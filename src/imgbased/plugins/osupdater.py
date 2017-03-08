#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# imgbase
#
# Copyright (C) 2014  Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Author(s): Fabian Deutsch <fabiand@redhat.com>
#

import logging
import glob
import hashlib
import os
import re
import shutil
import subprocess

from filecmp import dircmp

from .. import bootloader, utils
from ..lvm import LVM
from ..naming import Image
from ..volume import Volumes
from ..utils import mounted, ShellVarFile, RpmPackageDb, copy_files, Fstab,\
    File, SystemRelease, Rsync, kernel_versions_in_path, IDMap, remove_file, \
    find_mount_target, Motd, LvmCLI, unmount


log = logging.getLogger(__package__)

paths = {"/var":           "15G",
         "/var/log":       "8G",
         "/var/log/audit": "2G",
         "/home":          "1G",
         "/tmp":           "2G"
         }


class SeparateVarPartition(Exception):
    pass


class BootPartitionRequires1G(Exception):
    pass


class ConfigMigrationError(Exception):
    pass


class BootSetupError(Exception):
    pass


class MissingKernelFilesError(BootSetupError):
    pass


def pre_init(app):
    app.imgbase.hooks.create("os-upgraded",
                             ("previous-lv_fullname", "new-lv_fullname"))


def init(app):
    app.imgbase.hooks.connect("new-layer-added", on_new_layer)
    app.imgbase.hooks.connect("pre-layer-removed", on_remove_layer)
    app.imgbase.hooks.connect("post-init-layout", on_post_init_layout)


def on_new_layer(imgbase, previous_lv, new_lv):
    log.debug("Got: %s and %s" % (new_lv, previous_lv))

    # FIXME this can be improved by providing a better methods in .naming
    new_layer = Image.from_lv_name(new_lv.lv_name)
    previous_layer_lv = \
        imgbase._lvm_from_layer(imgbase.naming.layer_before(new_layer))
    try:
        # Some change in managed nodes is blapping /dev/mapper. Add it back
        # so LVM and /dev/mapper agree
        LvmCLI.vgchange(["-ay"])
        remediate_etc(imgbase)
        check_nist_layout(imgbase)
        migrate_var(imgbase, new_lv)
        migrate_etc(imgbase, new_lv, previous_layer_lv)
    except:
        log.exception("Failed to migrate etc")
        raise ConfigMigrationError()

    if not os.path.ismount("/var"):
        raise SeparateVarPartition(
            "\nIt's required /var as separate mountpoint!"
            "\nPlease check documentation for more details!"
        )

    try:
        adjust_mounts_and_boot(imgbase, new_lv, previous_layer_lv)
    except:
        # FIXME Handle and rollback
        log.exception("Failed to update OS")
        raise BootSetupError()


def on_post_init_layout(imgbase, existing_lv, new_base, new_layer):
    log.debug("Handling post-init-layout")

    # We need to bind /etc, to ensure all later changes
    # land in the new layer
    # Get the LV of the new layer
    new_lv = imgbase._lvm_from_layer(new_layer)
    # Now mount the LV to a temporary target
    new_fs = utils.MountPoint(new_lv.path)
    new_fs.mount()
    # Now bind mount /etc of the new LV over the existing /etc
    new_etc = utils.MountPoint(new_fs.path("/etc"),
                               target="/etc",
                               options="bind")
    new_etc.mount()


def check_nist_layout(imgbase):
    to_create = []

    for path in paths.keys():
        if not os.path.ismount(path):
            to_create.append(path)

    if to_create:
        v = Volumes(imgbase)
        for t in to_create:
            log.debug("Creating %s as %s" % (t, paths[t]))
            v.create(t, paths[t])


def migrate_var(imgbase, new_lv):
    def strip(s):
        return re.sub(r'^/tmp/mnt.*?/', '', s)

    log.debug("Syncing items present in the new /var which are not "
              "present in the existing FS")
    with mounted(new_lv.path) as new_fs:
        for cur, _dirs, files in os.walk(new_fs.path("/var")):
            for d in _dirs:
                newlv_path = "/".join([cur, d])
                realpath = "/".join([strip(cur), d])
                if not os.path.exists(realpath):
                    log.debug("Copying {} to {}".format(newlv_path, realpath))
                    if os.path.isdir(newlv_path):
                        shutil.copytree(newlv_path, realpath, symlinks=True)
                    else:
                        shutil.copy2(newlv_path, realpath)


def boot_partition_validation():
    """
    Function to validate all requirements for /boot partition
    """
    boot_dir = None
    bytes_in_1G = 1000**3

    for target in find_mount_target():
        if "boot" in target:
            boot_dir = target
            break

    if boot_dir is None:
        raise RuntimeError("findmnt: error, unable to find boot partition"
                           " in target!")

    st = os.statvfs(boot_dir)
    bytes_in_boot_partition = st.f_blocks * st.f_frsize

    if bytes_in_boot_partition < bytes_in_1G:
        # 1G is 1073741824 bytes. However, if users use size=1000
        # in anaconda kickstart won't work. Based on that, let's
        # inform to users it's required 1.1G (size=1100).
        log.error("New /boot must have at least 1.1G size")
        raise BootPartitionRequires1G


def remediate_etc(imgbase):
    # Find a list of files which have been erroneously copied and
    # look through old layers to find them
    layers = []

    def strip(s):
        s = re.sub(r'^/tmp/mnt.*?/', '', s)
        return re.sub(r'/+', '/', s)

    def md5sum(a, b):
        return hashlib.md5(open(a, 'rb').read()).hexdigest() == hashlib.md5(
            open(b, 'rb').read()).hexdigest()

    def diff_candidates(dc, problems, candidates=None):
        if candidates is None:
            candidates = set()
        if dc.same_files:
            for l in sorted(dc.same_files):
                f = "{}/{}".format(dc.left, l)
                if not os.path.islink(f):
                    if strip(f) in problems and strip(f) not in candidates:
                        if md5sum(f, "{}/{}".format(dc.right, l)):
                            candidates.add(strip(f))
                            log.debug("Updating %s from the next "
                                      "layer" % ("{}".format(strip(f))))
        if dc.subdirs:
            for d in sorted(dc.subdirs.values()):
                diff_candidates(d, problems, candidates)

        return candidates

    def diff_problems(dc, problems=None):
        if problems is None:
            problems = []
        if dc.diff_files:
            for l in sorted(dc.diff_files):
                # This is annoying, but handle initiatorname.iscsi
                # specially, since it's generated on-the-fly and will
                # always match what's in the first factory, but we
                # actually don't want to copy it
                if not os.path.islink("{}/{}".format(dc.left, l)) and \
                        "initiatorname.iscsi" not in l:
                    problems.append("{}/{}".format(strip(dc.left), l))
        if dc.subdirs:
            for d in sorted(dc.subdirs.values()):
                diff_problems(d, problems)

        return problems

    def find_candidates(m, n, problems):
        return diff_candidates(dircmp("{}/etc".format(m),
                                      "{}/usr/share/factory/etc".format(m)),
                               problems)

    def find_problems(m, n):
        problems = diff_problems(dircmp("{}/etc".format(m),
                                        "{}/usr/share/factory/etc".format(n)))
        candidates = find_candidates(m, n, problems)
        return candidates

    def check_layers(m, n):
        candidates = find_problems(m.path("/"), n.path("/"))
        for c in sorted(candidates):
            copy_from = n.path("/usr/share/factory") + c
            copy_to = n.path("/") + c

            log.debug("Copying %s to %s" % (copy_from, copy_to))
            shutil.copy2(copy_from, copy_to)

    tree = imgbase.naming.tree()

    for t in tree:
        for l in t.layers:
            layers.append(l)

    for idx in range(len(layers[:-1])):
        log.debug("Checking %s" % layers[idx])
        with mounted(imgbase._lvm_from_layer(layers[idx]).path) as m, \
                mounted(imgbase._lvm_from_layer(layers[idx+1]).path) as n:
                    # Resync the files we changed on the last pass
                    r = Rsync(checksum_only=True)
                    r.sync(m.path("/etc"), n.path("/etc"))

                    check_layers(m, n)


def migrate_etc(imgbase, new_lv, previous_lv):
    # Build a list of files in /etc which have been modified,
    # or which don't exist in the new filesystem, and only copy those
    changed = []

    def strip(s):
        return re.sub(r'^/tmp/mnt.*?/', '', s)

    def changed_and_new(dc):
        if dc.left_only:
            changed.extend(["{}/{}".format(strip(dc.left), f)
                            for f in dc.left_only])
        if dc.diff_files:
            changed.extend(["{}/{}".format(strip(dc.left), f)
                            for f in dc.diff_files])
        if dc.subdirs:
            for d in dc.subdirs.values():
                changed_and_new(d)

    log.debug("Migrating etc (%s -> %s)" % (previous_lv, new_lv))
    with mounted(new_lv.path) as new_fs,\
            mounted(previous_lv.path) as old_fs:
        old_etc = old_fs.path("/etc")
        new_etc = new_fs.path("/etc")

        old_rel = SystemRelease(old_etc + "/system-release-cpe")
        new_rel = SystemRelease(new_etc + "/system-release-cpe")

        log.info("Verifying stream compatability")
        log.debug("%s vs %s" % (old_rel, new_rel))

        if not new_rel.is_supported_product():
            log.error("Unsupported product: %s" % new_rel)

        is_same_product = old_rel.PRODUCT == new_rel.PRODUCT

        if not is_same_product:
            log.error("The previous and new layers seem to contain "
                      "different products")
            log.error("Old: %s" % old_rel)
            log.error("New: %s" % new_rel)

        if is_same_product:
            # The IDMap check must be run before etc was copied!
            # The check relies on the fact that the old etc and new etc differ
            idmaps = IDMap(old_etc, new_fs.path("/usr/share/factory/etc"))
            if idmaps.has_drift():
                log.info("UID/GID drift was detected")
                log.debug("Drifted uids: %s gids: %s" %
                          idmaps.get_drift())
                changes = idmaps.fix_drift(new_fs.path("/"))
                if changes:
                    log.info("UID/GID adjustments were applied")
                    log.debug("Changed files: %s" % list(changes))
                else:
                    log.debug("No changes necessary")
            else:
                log.debug("No drift detected")

            log.info("Migrating /etc (from %r)" % previous_lv)

            changed_and_new(dircmp(old_etc,
                            old_fs.path("/") + "/usr/share/factory/etc/")
                            )

            required_files = ["/etc/passwd", "/etc/group", "/etc/fstab",
                              "/etc/shadow", "/etc/iscsi/initiatorname.iscsi"]

            # Comparisons against the first layer can leave these files out.
            # Ensure they're copied
            for f in required_files:
                log.debug("%s not in required_files, adding" % f)
                if f not in changed:
                    changed.append(f)

            # imgbase layout --init double-dips here. Make sure that it's
            # not actually the same filesystem
            if old_fs.source != new_fs.source:
                for c in changed:
                    copy_files(new_fs.path("/") + c, [old_fs.path("/") + c],
                               "-a", "-r")

        else:
            log.info("Just copying important files")
            copy_files(new_etc,
                       [old_etc + "/fstab",
                        old_etc + "/passwd",
                        old_etc + "/shadow",
                        old_etc + "/group"])

        log.info("Migrating /root")
        rsync = Rsync()
        rsync.sync(old_fs.path("/root/"), new_fs.path("/root"))

        log.info("Syncing systemd levels")
        fix_systemd_services(old_fs, new_fs)
        relocate_var_lib_yum(new_fs)

        with utils.bindmounted("/var", new_fs.path("/var")):
            hack_rpm_permissions(new_fs)

        Motd(new_etc + "/motd").clear_motd()


def fix_systemd_services(old_fs, new_fs):
    # Enabled systemd services are preserved with rsync, but services
    # which were disabled will be spuriously re-enabled after an
    # upgrade unless we do this. Check vs the factory in /usr/share/factory
    # so we can tell what changed
    diffs = []

    def strip(path):
        return strip_factory(re.sub(r'/tmp/.*?/', '/', path))

    def strip_factory(path):
        return re.sub(r'/usr/share/factory', '', path)

    def diff(dc):
        if dc.right_only:
            diffs.extend(["{}/{}".format(strip(dc.right), f)
                          for f in dc.right_only])
        if dc.subdirs:
            for d in dc.subdirs.values():
                diff(d)

    diff(dircmp(old_fs.target + "/etc/systemd",
                old_fs.target + "/usr/share/factory/etc/systemd")
         )

    for d in diffs:
        log.debug("Removing %s" % d)
        try:
            if os.path.exists(new_fs.path("/") + d):
                if os.path.isdir(new_fs.path("/") + d):
                    remove_file(new_fs.path("/") + d, dir=True)
                elif os.path.isfile(new_fs.path("/") + d):
                    remove_file(new_fs.path("/") + d)
        except:
            log.exception("Could not remove %s. Is it a read-only layer?")


def relocate_var_lib_yum(new_fs):
    path = "/var/lib/yum"
    # Check whether /var is a symlink to /usr/share, and move it if it is not
    # We could directly check this in new_fs, but this gets tricky with
    # symlinks, and it will already be present on new builds
    if not os.path.islink(path):
        log.debug("/var/lib/yum is not a link -- moving it")
        shutil.rmtree(path)
        os.mkdir(path)
        shutil.move(path, "/usr/share/yum")
        os.symlink("/usr/share/yum", "/var/lib/yum")


def hack_rpm_permissions(new_fs):
    # FIXME changing the uid/gid is dropping the setuid.
    # The following "solution" will use rpm to restore the
    # correct permissions:
    # rpm --setperms $(rpm --verify -qa | grep "^\.M\."
    #                  | cut -d "/" -f2- | while read p ;
    #                  do rpm -qf /$p ; done )
    def just_do(arg, **kwargs):
        DEVNULL = open(os.devnull, "w")
        arg = ["nsenter", "--root=" + new_fs.path("/"), "--wd=/"] + arg
        log.debug("Running %s" % arg)
        proc = subprocess.Popen(arg, stdout=subprocess.PIPE,
                                stderr=DEVNULL,
                                **kwargs).communicate()
        return proc[0]

    incorrect_groups = {"paths": [],
                        "verb": "--setugids"
                        }
    incorrect_paths = {"paths": [],
                       "verb": "--setperms"
                       }
    for line in just_do(["rpm", "--verify", "-qa"]).splitlines():
        _mode, _path = (line[0:13], line[13:])
        if _mode[1] == "M":
            incorrect_paths["paths"].append(_path)
        if _mode[6] == "G":
            incorrect_groups["paths"].append(_path)
    log.debug("Incorrect groups according to rpm: %s" %
              str(incorrect_groups["paths"]))
    log.debug("Incorrect paths according to rpm: %s" %
              str(incorrect_paths["paths"]))

    for pgroup in [incorrect_groups, incorrect_paths]:
        pkgs_req_update = just_do(["rpm", "-qf", "--queryformat",
                                   "%{NAME}\n"] +
                                  pgroup["paths"]).splitlines()
        pkgs_req_update = list(set(pkgs_req_update))
        just_do(["rpm", pgroup["verb"]] + pkgs_req_update)


def adjust_mounts_and_boot(imgbase, new_lv, previous_lv):
    log.info("Inspecting if the layer contains OS data")

    """Add a new boot entry and update the layers /etc/fstab

    Another option is to use BLS - but it has issues with EFI:
    http://www.freedesktop.org/wiki/Specifications/BootLoaderSpec/
    """
    log.info("Adjusting mount and boot related points")

    new_lvm_name = new_lv.lvm_name

    oldrootsource = None
    with mounted(previous_lv.path) as oldrootmnt:
        oldfstab = Fstab("%s/etc/fstab" % oldrootmnt.target)
        if not oldfstab.exists():
            log.warn("No old fstab found, skipping os-upgrade")
            return

        log.debug("Found old fstab: %s" % oldfstab)
        rootentry = oldfstab.by_target("/")
        log.debug("Found old rootentry: %s" % rootentry)
        oldrootsource = rootentry.source
        log.debug("Old root source: %s" % oldrootsource)

        old_grub = ShellVarFile("%s/etc/default/grub" % oldrootmnt.target)
        old_grub_append = ""
        if old_grub.exists():
            old_grub_append = \
                old_grub.get("GRUB_CMDLINE_LINUX", "")
            log.debug("Old def grub: %s" % old_grub_append)

    def update_fstab(newroot):
        newfstab = Fstab("%s/etc/fstab" % newroot)

        if not newfstab.exists():
            log.info("The new layer contains no fstab, skipping.")
            return

        log.debug("Checking new fstab: %s" % newfstab)
        log.info("Updating fstab of new layer")
        rootentry = newfstab.by_target("/")
        rootentry.source = new_lv.path
        newfstab.update(rootentry)

        # Ensure that discard is used
        # This can also be done in anaconda once it is fixed
        for tgt in ["/", "/var"]:
            e = newfstab.by_target(tgt)
            if "discard" not in e.options:
                e.options += ["discard"]
                newfstab.update(e)

    def update_grub_default(newroot):
        defgrub = ShellVarFile("%s/etc/default/grub" % newroot)

        if not defgrub.exists():
            log.info("No grub foo found, not updating and not " +
                     "creating a boot entry.")
            return

        log.debug("Checking grub defaults: %s" % defgrub)
        defgrub.set("GRUB_CMDLINE_LINUX", old_grub_append)
        oldrootlv = LVM.LV.try_find(oldrootsource)
        log.debug("Found old root lv: %s" % oldrootlv)
        # FIXME this is quite greedy
        if oldrootlv.lvm_name in defgrub.contents:
            log.info("Updating default/grub of new layer")
            defgrub.replace(oldrootlv.lvm_name,
                            new_lvm_name)
        else:
            log.info("No LVM part found in grub default")
            log.debug("Contents: %s" % defgrub.contents)
            oldcmd = defgrub.get("GRUB_CMDLINE_LINUX", "")
            defgrub.set("GRUB_CMDLINE_LINUX",
                        oldcmd.replace('"', "") + " rd.lvm.lv=" + new_lvm_name)

    def copy_kernel(newroot):
        if not File("%s/boot" % newroot).exists():
            log.info("New root does not contain a kernel, skipping.")
            return

        bootdir = "/boot/%s" % new_lv.lv_name
        try:
            # FIXME we could work with globbing as well
            pkgs = RpmPackageDb()
            pkgs.root = newroot

            pkgfiles = pkgs.get_files("kernel")
            if not pkgfiles:
                log.info("No kernel found on %s" % new_lv)
                return

            kfiles = __check_kernel_files(pkgfiles, newroot)

            os.mkdir(bootdir)
            copy_files(bootdir, kfiles)
        except:
            log.warn("No kernel found in %s" % new_lv, exc_info=True)
            log.debug("Kernel copy failed", exc_info=True)
            return

        log.info("Regenerating initramfs ...")

        def chroot(*args):
            log.debug("Running: %s" % str(args))
            with utils.bindmounted(bootdir, newroot + "/boot"):
                return utils.nsenter(args, root=newroot)

        kvers = kernel_versions_in_path(bootdir)
        kver = kvers.pop()
        log.debug("Found kvers: %s" % kvers)
        log.debug("Using kver: %s" % kver)
        initrd = "/boot/initramfs-%s.img" % kver
        chroot("dracut", "-f", initrd, "--kver", kver)

        # Copy the .hmac file for FIPS until rhbz#1415032 is resolved
        # Since .hmac is a plain checksum pointing at a bare path in /boot,
        # we need to copy everything
        with utils.bindmounted("/boot", newroot + "/boot"):
            log.debug("Copying FIPS files")
            files = glob.glob("/boot/%s/*" % new_lv.lv_name) + \
                glob.glob("/boot/%s/.*" % new_lv.lv_name)
            log.debug(files)
            for f in files:
                log.debug("Copying %s to /boot" % f)
                shutil.copy2(f, "/boot")

    def __check_kernel_files(pkgfiles, newroot):
        kfiles = ["%s/%s" % (newroot, f)
                  for f in pkgfiles
                  if f.startswith("/boot/")]

        log.debug("Found kernel files: %s" % kfiles)
        log.debug("Making sure kernel files exist")

        if os.path.ismount("/boot"):
            log.info("/boot is mounted. Checking for the files there")

            bootfiles = [f for f in pkgfiles if f.startswith("/boot")]

            if all([File(f).exists() for f in bootfiles]):
                log.info("All kernel files found on the mounted /boot "
                         "filesystem. Using those")
                kfiles = bootfiles

        if not all([File(f).exists() for f in kfiles]):
            log.info("Some kernel files are not found on %s and /boot"
                     % newroot)
            raise MissingKernelFilesError("Failed to find kernel and initrd")

        return kfiles

    def add_bootentry(newroot):
        def _find_kfile(entry, kfiles):
            return [f for f in kfiles if entry in f].pop()\
                .replace("/boot", "").lstrip("/")
        if not File("%s/boot" % newroot).exists():
            log.info("New root does not contain a /boot, skipping.")
            return

        bootdir = "/boot/%s" % new_lv.lv_name
        log.debug("Looking for kernel dir %s" % bootdir)
        if not os.path.isdir(bootdir):
            log.warn("No kernel found, a boot entry "
                     "was *not* created")
            return

        title = None
        try:
            title = utils.BuildMetadata(newroot).get("nvr")
        except:
            log.warn("Failed to retrieve metadata", exc_info=True)

        if not title:
            log.debug("Checking OS release")
            osrel = ShellVarFile("%s/etc/os-release" % newroot)
            if osrel.exists():
                name = osrel.parse()["PRETTY_NAME"].strip()
                title = "%s (%s)" % (new_lvm_name, name)

        if not title:
            log.debug("Checking system release")
            sysrel = File("%s/etc/system-release" % newroot)
            if sysrel.exists():
                title = "%s (%s)" % (new_lvm_name,
                                     sysrel.contents.strip())

        if not title:
            log.warn("Failed to create pretty name, falling back to "
                     "volume name.")
            title = new_lvm_name

        log.info("Adding a boot entry")
        kfiles = glob.glob(bootdir + "/*")
        # For the loader we are relative to /boot and need to
        # strip this part from the paths
        vmlinuz = _find_kfile("vmlinuz", kfiles)
        initrd = _find_kfile("initramfs", kfiles)
        # FIXME default/grub cmdine and /etc/kernel… /var/kernel…
        grub_append = ShellVarFile("%s/etc/default/grub" % newroot)\
            .get("GRUB_CMDLINE_LINUX", "").strip('"').split()
        append = "rd.lvm.lv={0} root=/dev/{0}".format(new_lvm_name)\
            .split()
        # Make sure we don't have duplicate args
        append = " ".join(list(set(grub_append).union(set(append))))
        loader = bootloader.Grubby()
        loader.add_entry(new_lv.lv_name, title, vmlinuz, initrd, append)
        loader.set_default(new_lv.lv_name)

    with mounted(new_lv.path) as newroot:
        with utils.ExitStack() as es:
            mounts = [es.enter_context(utils.bindmounted(path,
                      target=newroot.target + path))
                      for path in sorted(paths.keys())]
            update_fstab(newroot.target)
            update_grub_default(newroot.target)
            copy_kernel(newroot.target)
            add_bootentry(newroot.target)

            try:
                boot_partition_validation()
            except:
                raise

            del mounts

    unmount("/tmp")

    imgbase.hooks.emit("os-upgraded",
                       previous_lv.lv_name,
                       new_lvm_name)


def on_remove_layer(imgbase, lv_fullname):
    remove_boot(imgbase, lv_fullname)


def remove_boot(imgbase, lv_fullname):
    lv_name = LVM.LV.from_lvm_name(lv_fullname).lv_name
    assert lv_name

    bootdir = "/boot/%s" % lv_name

    loader = bootloader.Grubby()
    loader.remove_entry(lv_name)

    assert bootdir.strip("/") != "boot"
    log.debug("Removing kernel dir: %s" % bootdir)
    shutil.rmtree(bootdir)

# vim: sw=4 et sts=4:

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

import errno
import filecmp
import logging
import glob
import hashlib
import os
import re
import rpm
import shutil
import subprocess

from filecmp import dircmp
from tempfile import mkdtemp

from .. import bootloader, timeserver, utils
from ..config import paths
from ..lvm import LVM
from ..naming import Image
from ..volume import Volumes
from ..command import just_do
from ..openscap import OSCAPScanner
from ..utils import mounted, ShellVarFile, RpmPackageDb, copy_files, Fstab,\
    File, SystemRelease, Rsync, kernel_versions_in_path, IDMap, remove_file, \
    find_mount_target, Motd, LvmCLI, SELinuxDomain, ThreadRunner, \
    thread_group_handler, systemctl


log = logging.getLogger(__package__)


class SeparateVarPartition(Exception):
    pass


class BootPartitionRequires1G(Exception):
    pass


class ConfigMigrationError(Exception):
    pass


class BootSetupError(Exception):
    pass


class NistSetupError(Exception):
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

    vdsm_is_active = preprocess(imgbase)
    previous_layer_lv = get_prev_layer_lv(imgbase, new_lv)

    try:
        # Some change in managed nodes is blapping /dev/mapper. Add it back
        # so LVM and /dev/mapper agree
        set_thinpool_profile(imgbase, new_lv)
        mknod_dev_urandom(new_lv)

        threads = []
        threads.append(ThreadRunner(remediate_etc, imgbase))
        threads.append(ThreadRunner(migrate_var, imgbase, new_lv))

        thread_group_handler(threads, ConfigMigrationError)

        check_nist_layout(imgbase, new_lv)

        threads = []
        threads.append(ThreadRunner(migrate_etc, imgbase, new_lv,
                                    previous_layer_lv))
        threads.append(ThreadRunner(migrate_state, new_lv, previous_layer_lv,
                                    "/root/"))
        threads.append(ThreadRunner(migrate_state, new_lv, previous_layer_lv,
                                    "/usr/share/rhn/", exclude=["*.py*"]))
        threads.append(ThreadRunner(relocate_update_manager, new_lv))

        thread_group_handler(threads)
    except:
        log.exception("Failed to migrate etc")
        raise ConfigMigrationError()

    postprocess(new_lv)
    migrate_boot(imgbase, new_lv, previous_layer_lv)
    imgbase.protect_init_lv()
    restart_vdsm(vdsm_is_active)


def preprocess(imgbase):
    if not os.path.ismount("/var"):
        raise SeparateVarPartition(
            "\nIt's required /var as separate mountpoint!"
            "\nPlease check documentation for more details!"
        )
    # Protect /var from being unmounted
    utils.ExternalBinary().mount(["--make-rprivate", "/var"])
    # vdsm can deactivate our LVs during upgrades in some cases.  Since the
    # host is in maintenance mode during upgrades, we can safely stop its
    # services, and restart them when we're done (see vdsm's %post for details)
    vdsm_is_active = systemctl.is_active("vdsmd")
    [systemctl.stop(unit) for unit in ("vdsmd", "supervdsmd", "vdsm-network")]
    LvmCLI.vgchange(["-ay", "--select", "vg_tags = %s" % imgbase.vg_tag])
    return vdsm_is_active


def get_prev_layer_lv(imgbase, new_lv):
    new_layer = Image.from_lv_name(new_lv.lv_name)
    layer_before = imgbase.naming.layer_before(new_layer)
    previous_layer_lv = imgbase._lvm_from_layer(layer_before)
    # Try to use current_layer if it exists (upgrades only)
    try:
        previous_layer_lv = imgbase._lvm_from_layer(imgbase.current_layer())
    except Exception:
        pass
    return previous_layer_lv


def mknod_dev_urandom(new_lv):
    with mounted(new_lv.path) as new_fs:
        devurandom = "{}/dev/urandom".format(new_fs.target)
        utils.ExternalBinary().mknod([devurandom, "c", "1", "9"])


def restart_vdsm(vdsm_is_active):
    try:
        utils.ExternalBinary().mount(["--make-rshared", "/var"])
    except Exception:
        log.warn("Could not restore mount propagation on /var, ignoring")

    if vdsm_is_active:
        try:
            systemctl.start("vdsmd")
        except Exception:
            log.warn("vdsmd failed to start, a reboot is required")
    else:
        log.info("vdsmd was not active, skipping restart")


def postprocess(new_lv):
    def _reconfigure_vdsm():
        env = os.environ.copy()
        env["SYSTEMD_IGNORE_CHROOT"] = "1"
        with utils.bindmounted("/proc", new_fs.target + "/proc"):
            with utils.bindmounted("/run", new_fs.target + "/run"):
                just_do(["vdsm-tool", "configure", "--force"],
                        new_root=new_fs.path("/"), environ=env)

    def _apply_scap_profile():
        OSCAPScanner().process(new_fs.path("/"))

    def _permit_root_login():
        f = File(new_fs.path("/etc/ssh/sshd_config"))
        regex = re.compile("\s*(PermitRootLogin)\s+(yes|no|without-password)")
        data = ""
        updated = False
        for line in f.lines():
            line = line.strip()
            if line and line[0] == "#":
                data += line + "\n"
                continue
            if regex.search(line):
                if not updated:
                    data += "PermitRootLogin yes\n"
                    updated = True
            else:
                data += line + "\n"
        if not updated:
            data += "PermitRootLogin yes\n"
        f.write(data)

    def _disable_os_probes():
        grub_scripts = ["10_linux", "30_os-prober"]
        for scr in grub_scripts:
            f = File(new_fs.path(os.path.join("/etc/grub.d", scr)))
            if f.exists():
                f.chmod(0o644)

    def _clear_libvirt_cache():
        log.debug("Clearing the libvirt cache")
        cachedir = "/var/cache/libvirt/qemu/capabilities"
        if not os.path.isdir(cachedir):
            return
        for f in os.listdir(cachedir):
            path = os.path.join(cachedir, f)
            try:
                if os.path.isfile(path):
                    os.unlink(path)
            except OSError as e:
                log.warn("Failed to remove libvirt cache file %s, err=%s",
                         path, e.errno)

    def _run_ldconfig():
        log.debug("Running ldconfig on new layer")
        utils.ExternalBinary().ldconfig(["-r", new_fs.path("/")])

    def _install_update_rpm():
        update_rpm = os.getenv("IMGBASED_IMAGE_UPDATE_RPM")
        if not update_rpm:
            return
        # Grab the first update rpm
        rpms = list(set(update_rpm.splitlines()))
        if len(rpms) > 1:
            log.warn("Received multiple update rpms %s", rpms)
        log.debug("Installing image-update rpm from %s", rpms[0])
        utils.ExternalBinary().rpm(["-U", "--quiet", "--justdb", "--root",
                                    new_fs.path("/"), rpms[0]])

    with mounted(new_lv.path) as new_fs:
        _reconfigure_vdsm()
        _apply_scap_profile()
        _permit_root_login()
        _disable_os_probes()
        _run_ldconfig()
        _install_update_rpm()
    _clear_libvirt_cache()


def migrate_boot(imgbase, new_lv, previous_layer_lv):
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


def set_thinpool_profile(imgbase, new_lv):
    pool = imgbase._thinpool()
    img_profile = imgbase.thinpool_profile
    cur_profile = pool.profile()
    if not cur_profile:
        with mounted(new_lv.path) as new_fs:
            prof_dir = new_fs.path("/etc/lvm/profile")
            config = "config {profile_dir = \"%s\"}" % prof_dir
            log.debug("Pool %s: setting profile to %s", pool, img_profile)
            pool.set_profile(img_profile, config)
    else:
        if cur_profile != img_profile:
            log.warn("Unknown profile set for thinpool: %s", cur_profile)


def check_nist_layout(imgbase, new_lv):
    to_create = []

    for path in sorted(paths.keys()):
        if not os.path.ismount(path):
            to_create.append(path)

    with mounted(new_lv.path) as new_fs:
        if to_create:
            # lvm.conf has a breaking change in 7.4.
            # work around it
            config_path = mkdtemp()

            lvm_config_path = "/etc/lvm/lvm.conf"

            original_config = "{}/lvm.conf".format(config_path)
            new_config = "{}/lvm.conf.new".format(config_path)

            shutil.copy2(lvm_config_path, original_config)
            with utils.bindmounted(new_fs.path("/etc"), "/etc"):
                shutil.copy2("/etc/lvm/lvm.conf", new_config)
                shutil.copy2(original_config, lvm_config_path)
                v = Volumes(imgbase)
                for t in to_create:
                    log.debug("Creating %s as %s" % (t, paths[t]))
                    v.create(t, paths[t]["size"], paths[t]["attach"])
                shutil.copy2(new_config, lvm_config_path)


def migrate_state(new_lv, previous_lv, path, exclude=None):
    log.debug("Migrating %s from the old image to the new image" % path)
    rsync = Rsync(exclude=exclude)
    with mounted(new_lv.path) as new_fs, mounted(previous_lv.path) as old_fs:
        old_path = old_fs.path(path)
        if os.path.isdir(old_path):
            rsync.sync(old_path, new_fs.path(path))


def migrate_rpm_files(new_root, files):
    if not files:
        log.debug("No rpm files to migrate")
        return
    log.debug("Migrating files by rpm databases: %s", files)
    rpmdb = RpmPackageDb()
    rpmdb.root = new_root
    rpms, unknown = rpmdb.get_query_files(files)
    ghost_files = {}
    conf_files = {}
    if rpms:
        ghost_files = rpmdb.get_ghost_files(rpms)
        conf_files = rpmdb.get_conf_files(rpms)
    for dst in files:
        if dst in ghost_files.keys() + unknown:
            log.debug("Skip %s, fflags=[%s]", dst, ghost_files.get(dst, ""))
            continue
        src = new_root + "/" + dst
        if os.path.islink(src):
            src_lnk = os.readlink(src)
            if os.path.islink(dst):
                if src_lnk != os.readlink(dst):
                    os.rename(dst, dst + ".imglnk")
                    os.symlink(src_lnk, dst)
                    log.debug("Updated symlink %s -> %s", dst, src_lnk)
            else:
                os.rename(dst, dst + ".imgbak")
                os.symlink(src_lnk, dst)
                log.debug("Updated symlink %s -> %s", dst, src_lnk)
            continue
        if os.path.samefile(src, dst) or filecmp.cmp(src, dst):
            continue
        dst_conf = conf_files.get(dst)
        if dst_conf and "n" in dst_conf:  # %config(noreplace)
            shutil.copy2(src, dst + ".imgnew")
            log.debug("Saved config file to %s.imgnew", dst)
            continue
        os.rename(dst, dst + ".imgbak")
        shutil.copy2(src, dst)
        log.debug("Updated file %s", dst)


def migrate_var(imgbase, new_lv):
    def strip(s):
        return re.sub(r'^/tmp/mnt.*?/', '', s)

    log.debug("Syncing items from the new /var")

    with mounted(new_lv.path) as new_fs:
        xfiles = []
        for cur, _dirs, files in os.walk(new_fs.path("/var")):
            for d in _dirs:
                newlv_path = "/".join([cur, d])
                realpath = "/".join([strip(cur), d])
                # Don't copy the libvirt/qemu cache to new layers on upgrades.
                # This is supposed to be checked by qemu/libvirt through a
                # ctime comparison, but is also cleared on RPM upgrades.
                #
                # Instead of deleting it, we can just skip the copy

                if not os.path.exists(realpath) and \
                        "cache/libvirt/qemu/capabilities" not in realpath:
                    log.debug("Copying {} to {}".format(newlv_path, realpath))
                    if os.path.isdir(newlv_path):
                        shutil.copytree(newlv_path, realpath, symlinks=True)
                    else:
                        shutil.copy2(newlv_path, realpath)
            for f in files:
                newlv_path = "/".join([cur, f])
                realpath = "/".join([strip(cur), f])
                if not os.path.exists(realpath):
                    log.debug("Copying {} to {}".format(newlv_path, realpath))
                    try:
                        shutil.copy2(newlv_path, realpath)
                    except IOError as e:
                        log.warn("Copy failed %s, err=%s", newlv_path, e.errno)
                        if e.errno != errno.ENOENT:
                            raise
                else:
                    xfiles.append(realpath)
        migrate_rpm_files(new_fs.path("/"), xfiles)


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
    critical_files = [r'.*?/initiatorname.iscsi$',
                      r'.*?group-?$',
                      r'.*?passwd-?$',
                      r'.*?shadow-?$',
                      r'.*?fstab$',
                      r'.*?ifcfg-.*$'
                      ]

    crits = [re.compile(f) for f in critical_files]

    layers = []

    def check_file(f):
        return any(c.match(f) for c in crits)

    def strip(s):
        s = re.sub(r'^/tmp/mnt.*?/', '', s)
        return re.sub(r'/+', '/', s)

    def sha256sum(a, b):
        chksum_a = hashlib.sha256(open(a, 'rb').read()).hexdigest()
        chksum_b = hashlib.sha256(open(b, 'rb').read()).hexdigest()
        return chksum_a == chksum_b

    def diff_candidates(dc, problems, candidates=None):
        if candidates is None:
            candidates = set()
        if dc.same_files:
            for l in dc.same_files:
                f = "{}/{}".format(dc.left, l)
                if not os.path.islink(f):
                    if strip(f) in problems and strip(f) not in candidates:
                        if sha256sum(f, "{}/{}".format(dc.right, l)):
                            candidates.add(strip(f))
                            log.debug("Updating %s from the next "
                                      "layer" % ("{}".format(strip(f))))
        if dc.subdirs:
            for d in dc.subdirs.values():
                diff_candidates(d, problems, candidates)

        return candidates

    def diff_problems(dc, problems=None):
        if problems is None:
            problems = []
        if dc.diff_files:
            for l in dc.diff_files:
                # This is annoying, but handle initiatorname.iscsi
                # specially, since it's generated on-the-fly and will
                # always match what's in the first factory, but we
                # actually don't want to copy it
                if not os.path.islink("{}/{}".format(dc.left, l)) and \
                        not check_file(l):
                    problems.append("{}/{}".format(strip(dc.left), l))
        if dc.subdirs:
            for d in dc.subdirs.values():
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
            if "targeted/active/modules" not in c:
                copy_from = n.path("/usr/share/factory") + c
                copy_to = n.path("/") + c

                log.debug("Copying %s to %s" % (copy_from, copy_to))
                if not filecmp.cmp(copy_from, copy_to):
                    shutil.copy2(copy_from, copy_to)
                else:
                    log.debug("Unable to copy {} to {}. Symlink from a "
                              "package rename?".format(copy_from, copy_to))

    def analyze_removals(dc, pre_files=None):
        if pre_files is None:
            pre_files = []
        if dc.left_only:
            for f in dc.left_only:
                log.debug("Planning to remove %s/%s" % (strip(dc.right), f))
                pre_files.append("{}/{}".format(strip(dc.right), f))
        if dc.subdirs:
            for d in dc.subdirs.values():
                analyze_removals(d, pre_files)

        return pre_files

    def perform_removals(rms, n):
        for f in rms:
            filename = "{}/{}".format(n.path("/"), f)
            if not os.path.exists("{}/usr/share/factory/{}".format(
                    n.path("/"), f)):
                delete = False
                if os.path.isfile(filename):
                    delete = True
                elif os.path.islink(filename):
                    link_path = os.readlink(filename)
                    if not os.path.exists("{}/{}".format(n.path("/"),
                                                         link_path)):
                        log.debug("{} is a broken symlink to {}. Removing "
                                  "it".format(filename, link_path))
                    delete = True

                if delete:
                    log.debug("os.unlink({})".format(filename))
                    os.unlink(filename)

    tree = imgbase.naming.tree()

    for t in tree:
        for l in t.layers:
            layers.append(l)

    for idx in range(len(layers[:-1])):
        log.debug("Checking %s" % layers[idx])
        with mounted(imgbase._lvm_from_layer(layers[idx]).path) as m, \
                mounted(imgbase._lvm_from_layer(layers[idx+1]).path) as n:
                    pre_files = analyze_removals(
                        dircmp("{}/etc".format(m.path("/")),
                               "{}/etc".format(n.path("/"))
                               )
                    )
                    # Resync the files we changed on the last pass
                    r = Rsync(checksum_only=True, update_only=True,
                              exclude=["*targeted/active/modules*",
                                       "*network-scripts/ifcfg-*"])
                    r.sync(m.path("/etc"), n.path("/etc"))

                    check_layers(m, n)
                    fix_systemd_services(m, n)
                    perform_removals(pre_files, n)


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

    def configure_versionlock():
        log.info("Configuring versionlock for %s" % new_fs.source)
        fmt = "{0}:{1.name}-{1.version}-{1.release}.{1.arch}\n"
        data = "# imgbased: versionlock begin for layer %s\n" % new_fs.source
        rpm.addMacro("_dbpath", new_fs.path("/usr/share/rpm"))
        for hdr in rpm.TransactionSet().dbMatch():
            if "image-update" in hdr.name.decode("utf-8"):
                continue
            data += fmt.format(hdr.epoch or "0", hdr)
        rpm.delMacro("_dbpath")
        data += "# imgbased: versionlock end\n"
        # versionlock.list must exist, so find which one should we use
        for d in ("/etc/yum/pluginconf.d", "/etc/dnf/plugins/"):
            f = File(os.path.join(new_fs.path(d), "versionlock.list"))
            if f.exists():
                f.write(data)
        # Make sure we follow obsoletes for `yum versionlock`
        conf = File(new_fs.path("/etc/yum/pluginconf.d/versionlock.conf"))
        if conf.exists():
            data = conf.contents.splitlines()
            pattern = re.compile("^follow_obsoletes\s*=\s*1")
            if not [x for x in data if pattern.search(x)]:
                conf.writen("follow_obsoletes = 1", mode="a")

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
            group_content = File(old_etc + "/group").read()
            passwd_content = File(old_etc + "/passwd").read()

            # The IDMap check must be run before etc was copied!
            # The check relies on the fact that the old etc and new etc differ
            idmaps = IDMap(old_etc, new_fs.path("/usr/share/factory/etc"))
            if idmaps.has_drift():
                log.info("UID/GID drift was detected")
                log.debug("Drifted uids: %s gids: %s" %
                          idmaps.get_drift())
                changes = idmaps.fix_drift(new_fs.path("/"))
                group_content, passwd_content = idmaps.group_content, \
                    idmaps.passwd_content
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
                if f not in changed and os.path.exists(f):
                    changed.append(f)

            # imgbase layout --init double-dips here. Make sure that it's
            # not actually the same filesystem
            if old_fs.source != new_fs.source:
                for c in changed:
                    d = c.replace("redhat-access-insights", "insights-client")
                    if "targeted/active/modules" not in c:
                        copy_files(new_fs.path("/") + d,
                                   [old_fs.path("/") + c], "-a", "-r")

            File(new_fs.path("/etc/group")).write(group_content)
            File(new_fs.path("/etc/passwd")).write(passwd_content)

        else:
            log.info("Just copying important files")
            copy_files(new_etc,
                       [old_etc + "/fstab",
                        old_etc + "/passwd",
                        old_etc + "/shadow",
                        old_etc + "/group"])

        configure_versionlock()

        log.info("Migrating /root")

        threads = []
        threads.append(ThreadRunner(migrate_ntp_to_chrony, new_lv))
        threads.append(ThreadRunner(run_rpm_perms, new_lv))
        threads.append(ThreadRunner(fix_systemd_services, old_fs, new_fs))
        threads.append(ThreadRunner(run_rpm_selinux_post, new_lv))

        thread_group_handler(threads)

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

    log.info("Syncing systemd levels")

    diff(dircmp(old_fs.target + "/etc/systemd",
                old_fs.target + "/usr/share/factory/etc/systemd")
         )

    for d in diffs:
        log.debug("Removing %s" % d)
        filename = os.path.basename(d)
        try:
            if os.path.exists(new_fs.path("/") + d):
                if os.path.isdir(new_fs.path("/") + d):
                    remove_file(new_fs.path("/") + d, dir=True)
                elif os.path.isfile(new_fs.path("/") + d):
                    remove_file(new_fs.path("/") + d)

            # EL updates can move some of these around. Firewalld goes from
            # basic.target.wants to multiuser.target.wants in 7.4. Check the
            # entire tree
            for root, dirs, files in os.walk(new_fs.path("/etc/systemd")):
                for d in dirs:
                    if d == filename:
                        log.debug("Found a disabled systemd service "
                                  "elsewhere. Removing it: %s" % filename)
                        remove_file(os.path.join(root, d), dir=True)
                for f in files:
                    if f == filename:
                        log.debug("Found a disabled systemd service "
                                  "elsewhere. Removing it: %s" % filename)
                        remove_file(os.path.join(root, f))
        except:
            log.exception("Could not remove %s. Is it a read-only layer?")


def run_rpm_selinux_post(new_lv):
    run_commands = []
    critical_commands = ["restorecon", "semodule", "semanage", "fixfiles",
                         "chcon", "vdsm-schema-cache-regenerate"]

    def filter_selinux_commands(rpms, scr_arg):
        for pkg, v in rpms.items():
            if any([c for c in critical_commands if c in v]):
                log.debug("Found a critical command in %s", pkg)
                run_commands.append("bash -c '{}' -- {}".format(v, scr_arg))

    selinux_enabled = utils.ExternalBinary().getenforce() != "Disabled"

    with mounted(new_lv.path) as new_fs:
        log.debug("Checking whether any %post scripts from the new image must "
                  "be run")
        rpmdb = RpmPackageDb()
        rpmdb.root = new_fs.path("/")

        postin = rpmdb.get_script_type('POSTIN')
        posttrans = rpmdb.get_script_type('POSTTRANS')

        filter_selinux_commands(postin, 1)
        filter_selinux_commands(posttrans, 0)

        with utils.bindmounted("/proc",
                               new_fs.target + "/proc"):
            with utils.bindmounted("/dev",
                                   new_fs.target + "/dev"):
                with utils.mounted("sys",
                                   target=new_fs.target + "/sys",
                                   fstype="sysfs"):
                    if selinux_enabled:
                        with utils.mounted("selinuxfs",
                                           target=new_fs.target +
                                           "/sys/fs/selinux",
                                           fstype="selinuxfs"):
                            for r in run_commands:
                                just_do(r, new_root=rpmdb.root, shell=True)

        if selinux_enabled:
            # this can unmount selinux. Make sure it's present
            if "/sys/fs/selinux" not in File("/proc/mounts").read():
                subprocess.call(["mount", "-t", "selinuxfs",
                                 "none", "/sys/fs/selinux"])

        subprocess.call(["mount", "-a"])


def relocate_update_manager(new_lv):
    paths = ["/var/lib/yum", "/var/lib/dnf"]
    # Check whether /var is a symlink to /usr/share, and move it if it is not
    # We could directly check this in new_fs, but this gets tricky with
    # symlinks, and it will already be present on new builds
    for path in paths:
        if not os.path.exists(path):
            continue
        usr_share = os.path.join("/usr/share", os.path.basename(path))
        if not os.path.islink(path):
            log.debug("%s is not a link -- moving it" % path)
            shutil.rmtree(path)
            os.mkdir(path)
            shutil.move(path, usr_share)
            os.symlink(usr_share, path)


def migrate_ntp_to_chrony(new_lv):
    try:
        systemctl.status("ntpd.service")
    except:
        log.debug("ntpd is disabled, not migrating conf to chrony")
        return
    with mounted(new_lv.path) as new_fs:
        if os.path.exists(new_fs.path("/") + "/etc/ntp.conf"):
            # Create a state directory to track migrations
            # /var is the right place for application-level data
            if not os.path.isdir("/var/lib/imgbased"):
                os.mkdir("/var/lib/imgbased")

            if not os.path.exists("/var/lib/imgbased/ntp-migrated"):
                log.debug("Migrating NTP configuration to chrony")
                c = timeserver.Chrony(new_fs.path("/") + "/etc/chrony.conf")

                c.from_ntp(timeserver.Ntp(new_fs.path("/") + "/etc/ntp.conf"))


def run_rpm_perms(new_lv):
    with mounted(new_lv.path) as new_fs:
        with utils.bindmounted("/var", new_fs.path("/var"), rbind=True):
            hack_rpm_permissions(new_fs)


def hack_rpm_permissions(new_fs):
    # FIXME changing the uid/gid is dropping the setuid.
    # The following "solution" will use rpm to restore the
    # correct permissions:
    # rpm --setperms $(rpm --verify -qa | grep "^\.M\."
    #                  | cut -d "/" -f2- | while read p ;
    #                  do rpm -qf /$p ; done )
    incorrect_groups = {"paths": [],
                        "verb": "--setugids"
                        }
    incorrect_paths = {"paths": [],
                       "verb": "--setperms"
                       }
    new_root = new_fs.path("/")
    for line in just_do(["rpm", "--verify", "-qa", "--nodeps", "--nodigest",
                         "--nofiledigest", "--noscripts",
                         "--nosignature"], new_root=new_root).splitlines():
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
                                  "%{NAME}\n"] + pgroup["paths"],
                                  new_root=new_root).splitlines()
        pkgs_req_update = list(set(pkgs_req_update))
        if pkgs_req_update:
            just_do(["rpm", pgroup["verb"]] + pkgs_req_update,
                    new_root=new_root)


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
        targets = list(paths.keys()) + ["/"]
        for tgt in targets:
            try:
                e = newfstab.by_target(tgt)
                if "discard" not in e.options:
                    e.options += ["discard"]
                    newfstab.update(e)
            except KeyError:
                # Created with imgbased.volume?
                log.debug("{} not found in /etc/fstab. "
                          "ot created by Anaconda".format(tgt))
                from six.moves.configparser import ConfigParser
                c = ConfigParser()
                c.optionxform = str

                sub = re.sub(r'^/', '', tgt)
                sub = re.sub(r'/', '-', sub)
                fname = "{}/etc/systemd/system/{}.mount".format(newroot, sub)
                c.read(fname)

                if 'discard' not in c.get('Mount', 'Options'):
                    c.set('Mount', 'Options',
                          ','.join([c.get('Mount', 'Options'), 'discard']))

                with open(fname, 'w') as mountfile:
                    c.write(mountfile)

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

            pkgfiles = pkgs.get_files(pkgs.get_whatprovides("kernel"))
            if not pkgfiles:
                log.info("No kernel found on %s" % new_lv)
                return

            kfiles = __check_kernel_files(pkgfiles, newroot)

            if not os.path.exists(bootdir):
                os.mkdir(bootdir)
            copy_files(bootdir, kfiles)
        except:
            log.warn("No kernel found in %s" % new_lv, exc_info=True)
            log.debug("Kernel copy failed", exc_info=True)
            return

        log.info("Regenerating initramfs ...")

        def chroot(*args):
            log.debug("Running: %s" % str(args))
            with utils.bindmounted("/proc", newroot + "/proc"):
                with utils.bindmounted(bootdir, newroot + "/boot"):
                    return utils.nsenter(args, root=newroot)

        kvers = kernel_versions_in_path(bootdir)
        log.debug("Found kvers: %s" % kvers)
        for kver in kvers:
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
        def _find_kfiles(entry, kfiles):
            return sorted([f.replace("/boot", "").lstrip("/")
                           for f in kfiles if entry in f])

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
        kernels = _find_kfiles("vmlinuz", kfiles)
        ramdisks = _find_kfiles("initramfs", kfiles)
        # FIXME default/grub cmdine and /etc/kernel… /var/kernel…
        grub_append = ShellVarFile("%s/etc/default/grub" % newroot)\
            .get("GRUB_CMDLINE_LINUX", "").strip('"').split()
        append = "rd.lvm.lv={0} root=/dev/{0}".format(new_lvm_name)\
            .split()
        # Make sure we don't have duplicate args
        append = " ".join(list(set(grub_append).union(set(append))))
        loader = bootloader.Grubby()
        for vmlinuz, initrd in zip(kernels, ramdisks):
            loader.add_entry(new_lv.lv_name, title, vmlinuz, initrd, append)
            loader.set_default(new_lv.lv_name)
        loader.remove_other_entries()

    def relabel_selinux(newroot):
        files = ["/etc/selinux/targeted/contexts/files/file_contexts",
                 "/etc/selinux/targeted/contexts/files/file_contexts.homedirs",
                 "/etc/selinux/targeted/contexts/files/file_contexts.local"]

        dirs = ["/etc",
                "/usr/bin",
                "/usr/libexec",
                "/usr/sbin",
                "/usr/share",
                "/var"]

        exclude_dirs = ["/usr/share/factory"]

        # Reduce the list to something subprocess can use directly

        log.debug("Relabeling selinux")

        with SELinuxDomain("setfiles_t") as dom:
            for fc in files:
                if os.path.exists(newroot + "/" + fc):
                    excludes = sum([["-e", d] for d in exclude_dirs], [])
                    dom.runcon(["chroot", newroot, "setfiles", "-v", fc] +
                               excludes + dirs)
                else:
                    log.debug("{} not found in new fs, skipping".format(fc))

    imgbase.hooks.emit("os-upgraded", previous_lv.lv_name, new_lvm_name)

    with mounted(new_lv.path) as newroot:
        with utils.bindmounted("/var", target=newroot.target + "/var",
                               rbind=True):
            update_fstab(newroot.target)
            update_grub_default(newroot.target)
            copy_kernel(newroot.target)
            relabel_selinux(newroot.target)
            add_bootentry(newroot.target)

            try:
                boot_partition_validation()
            except:
                raise


def on_remove_layer(imgbase, lv_fullname):
    remove_boot(imgbase, lv_fullname)


def remove_boot(imgbase, lv_fullname):
    lv_name = LVM.LV.from_lvm_name(lv_fullname).lv_name
    assert lv_name

    bootdir = "/boot/%s" % lv_name

    loader = bootloader.Grubby()
    loader.remove_entry(lv_name)

    assert bootdir.strip("/") != "boot"

    bootfiles = [os.path.basename(b) for b in glob.glob("%s/*" % bootdir)]

    bootfiles.extend([re.sub(r'(initramfs.*?).img', r'\1kdump.img', f)
                      for f in bootfiles if "initramfs" in f])

    for f in bootfiles:
        if os.path.isfile("/boot/%s" % f):
            log.debug("Removing extraneous boot file /boot/%s" % f)
            os.unlink("/boot/%s" % f)

    if os.path.exists(bootdir):
        log.debug("Removing kernel dir: %s" % bootdir)
        shutil.rmtree(bootdir)

# vim: sw=4 et sts=4:

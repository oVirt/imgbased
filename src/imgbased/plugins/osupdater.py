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
import os
import shutil
from .. import bootloader, utils
from ..lvm import LVM
from ..naming import Image
from ..utils import mounted, ShellVarFile, RpmPackageDb, copy_files, Fstab,\
    File, SystemRelease, Rsync, kernel_versions_in_path, IDMap


log = logging.getLogger(__package__)


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
        migrate_etc(imgbase, new_lv, previous_layer_lv)
    except:
        log.exception("Failed to migrate etc")
        raise ConfigMigrationError()

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


def migrate_etc(imgbase, new_lv, previous_lv):
    log.debug("Migrating etc (%s -> %s)" % (previous_lv, new_lv))
    with mounted(new_lv.path) as new_fs,\
            mounted(previous_lv.path) as old_fs:
        old_etc = old_fs.path("/etc")
        new_etc = new_fs.path("/etc")

        old_rel = SystemRelease(old_etc + "/system-release-cpe")
        new_rel = SystemRelease(new_etc + "/system-release-cpe")

        log.info("Verifying stream compatability")
        log.debug("%s vs %s" % (old_rel, new_rel))

        if new_rel.PRODUCT not in ["fedora", "centos"]:
            log.error("Unsupported üproduct: %s" % new_rel)

        is_same_product = old_rel.PRODUCT == new_rel.PRODUCT

        if not is_same_product:
            log.error("The previous and new layers seem to contain "
                      "different products")
            log.error("Old: %s" % old_rel)
            log.error("New: %s" % new_rel)

        if is_same_product:
            idmaps = IDMap(old_etc, new_etc)
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
            rsync = Rsync()
            # Don't copy release files to have up to date release infos
            rsync.exclude = ["etc/fedora-release*", "/etc/redhat-release*"]
            rsync.sync(old_etc + "/", new_etc)
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
        bfile = lambda n: [f for f in kfiles if n in f].pop()\
            .replace("/boot", "").lstrip("/")
        vmlinuz = bfile("vmlinuz")
        initrd = bfile("initramfs")
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
        with utils.bindmounted("/var", target=newroot.target + "/var"):
            update_fstab(newroot.target)
            update_grub_default(newroot.target)
            copy_kernel(newroot.target)
            add_bootentry(newroot.target)

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

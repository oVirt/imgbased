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
import sh
import glob
import os
from .. import bootloader
from ..lvm import LVM
from ..utils import mounted, ShellVarFile, RpmPackageDb, copy_files, Fstab,\
    File, SystemRelease, Rsync


log = logging.getLogger(__package__)


def pre_init(app):
    app.imgbase.hooks.create("os-upgraded",
                             ("previous-lv_fullname", "new-lv_fullname"))


def init(app):
    app.hooks.connect("register-checks", on_register_checks)
    app.imgbase.hooks.connect("new-layer-added", on_new_layer)


def on_register_checks(app, register):
    @register
    def bls_check():
        log.info("Checking bootloader configuration")
        fail = True
        try:
            sh.grep("-e" "syslinux_source|bls_import",
                    glob.glob("/etc/grub.d/*"))
            fail = False
        except:
            log.warning("Bootloader is not configured propperly")
            print("cat <<EOF > /etc/grub.d/50_imgbased")
            print("echo -e syslinux_source /syslinux.cfg")
            print("echo -e bls_import")
            print("EOF")
            print("chmod a+x /etc/grub.d/50_imgbased")
        return fail

    @register
    def mount_check():
        log.info("Checking if 'discard' is used")
        # FIXME we need to check mopts of correct path
        fail = "discard" not in sh.findmnt("-no", "options").split(",")
        if fail:
            log.warning("/ is not mounted with discard")
            print(sh.findmnt("/"))
        return fail


def on_new_layer(imgbase, previous_lv_lvm_name, new_lv_lvm_name):
    # previous_lv = LVM.LV.from_lvm_name(previous_lv_lvm_name)
    new_lv = LVM.LV.from_lvm_name(new_lv_lvm_name)

    new_layer = imgbase.naming.image_from_name(new_lv.lv_name)
    previous_layer = imgbase.naming.layer_before(new_layer)

    migrate_etc(imgbase, new_layer, previous_layer)
    adjust_mounts_and_boot(imgbase, new_layer, previous_layer)


def migrate_etc(imgbase, new_layer, previous_layer):
    with mounted(new_layer.lvm.path) as new_fs,\
            mounted(previous_layer.lvm.path) as old_fs:
        old_etc = old_fs.target + "/etc"
        new_etc = new_fs.target + "/etc"

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
            log.info("Migrating /etc")
            rsync = Rsync()
            # Don't copy release files to have up to date release infos
            rsync.exclude = ["etc/*-release*"]
            rsync.sync(old_etc + "/", new_etc)
        else:
            log.info("Just copying important files")
            copy_files(new_etc,
                       [old_etc + "/fstab",
                        old_etc + "/passwd",
                        old_etc + "/shadow",
                        old_etc + "/group"])


def adjust_mounts_and_boot(imgbase, new_layer, previous_layer):
    log.info("Inspecting if the layer contains OS data")

    """Add a new BLS based boot entry and update the layers /etc/fstab

    http://www.freedesktop.org/wiki/Specifications/BootLoaderSpec/
    """
    log.info("Adjusting mount and boot related points")

    new_lv = new_layer.lvm
    new_lvm_name = new_lv.lvm_name

    oldrootsource = None
    with mounted(previous_layer.lvm.path) as oldrootmnt:
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

    def copy_kernel(newroot):
        if not File("%s/boot" % newroot).exists():
            log.info("New root does not contain a kernel, skipping.")
            return

        bootdir = "/boot/%s" % new_lv.lv_name
        try:
            chroot = \
                sh.systemd_nspawn.bake("-q",
                                       "--bind", "/boot",
                                       "--bind", "%s:/image" % newroot,
                                       "-D", newroot)

            # FIXME we could work with globbing as well
            pkgs = RpmPackageDb()
            pkgs._rpm_cmd = chroot.bake("rpm")

            pkgfiles = pkgs.get_files("kernel")
            if not pkgfiles:
                log.info("No kernel found on %s" % new_layer)
                return

            kfiles = ["%s/%s" % (newroot, f)
                      for f in pkgfiles
                      if f.startswith("/boot/")]
            log.debug("Found kernel files: %s" % kfiles)

            chroot("mkdir", bootdir)
            copy_files(bootdir, kfiles)
        except:
            log.warn("No kernel found in %s" % new_lv, exc_info=True)
            log.debug("Kernel copy failed", exc_info=True)
            return

        log.info("FIXME Regenerating initramfs")
        chroot = \
            sh.systemd_nspawn.bake("-q",
                                   "--bind", "%s:/boot" % bootdir,
                                   "-D", newroot)
#        kfiles = glob.glob(bootdir + "/*")
#        bfile = lambda n: [f for f in kfiles if n in f].pop()\
#            .replace(newroot, new_lvm_name).lstrip("/")
#        vmlinuz = bfile("vmlinuz")
#        initrd = bfile("init")
        # FIXME chroot("dracut", image, "--kver", kver)

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

        log.debug("Checking os-release")
        osrel = ShellVarFile("%s/etc/os-release" % newroot)
        if osrel.exists():
            name = osrel.parse()["PRETTY_NAME"]
            title = "%s (on %s)" % (name, new_lvm_name)
        else:
            log.info("No os-release file exists, can not create "
                     "pretty name")
            title = new_lvm_name

        log.info("Adding a boot entry")
        kfiles = glob.glob(bootdir + "/*")
        # For the loader we are relative to /boot and need to
        # strip this part from the paths
        bfile = lambda n: [f for f in kfiles if n in f].pop()\
            .replace("/boot", "").lstrip("/")
        vmlinuz = bfile("vmlinuz")
        initrd = bfile("init")
        # FIXME default/grub cmdine and /etc/kernel… /var/kernel…
        grub_append = ShellVarFile("%s/etc/default/grub" % newroot)\
            .get("GRUB_CMDLINE_LINUX", "").strip('"').split()
        append = "rd.lvm.lv={0} root=/dev/{0}".format(new_lvm_name)\
            .split()
        # Make sure we don't have duplicate args
        append = " ".join(list(set(grub_append).union(set(append))))
        loader = bootloader.SyslinuxBootloader()
        loader.add_entry(title, vmlinuz, initrd, append)
        loader.set_default(title)

    with mounted(new_lv.path) as newroot:
        update_fstab(newroot.target)
        update_grub_default(newroot.target)
        copy_kernel(newroot.target)
        add_bootentry(newroot.target)

    imgbase.hooks.emit("os-upgraded",
                       previous_layer.lvm.lv_name,
                       new_lvm_name)

# vim: sw=4 et sts=4:

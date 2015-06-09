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
import subprocess
import os
import re
import io
import sh
import glob
import datetime
from .hooks import Hooks
from . import bootloader
from .utils import ExternalBinary, File, \
    mounted, find_mount_source, ShellVarFile, Fstab
from .lvm import LVM

import logging


log = logging.getLogger(__package__)


class ImageLayers(object):
    debug = False
    dry = False

    hooks = None

    vg_tag = "imgbased:vg"
    thinpool_tag = "imgbased:pool"

    run = None

    bootloader = None

    def __init__(self):
        self.hooks = Hooks(self)

        # A default wildcard hook is to also trigger
        # filesystem based hooks
        def _trigger_fs(app, name, *args):
            """Trigger internal/pythonic hooks
            """
            if not os.path.exists(self.hooksdir):
                return
            for handler in os.listdir(self.hooksdir):
                script = os.path.join(self.hooksdir, handler)
                log.debug("Triggering: %s (%s %s)" % (script, name, args))
                self.context.run.call([script, name] + list(args))
        self.hooks.create(None, _trigger_fs)

        #
        # Add availabel hooks
        #
        self.hooks.create("new-layer-added",
                          ("old-target", "new-lv", "new-target"))
        self.hooks.create("new-base-added",
                          ("new-lv",))
        self.hooks.create("new-base-with-tree-added",
                          ("new-fs",))

        self.run = ExternalBinary()
        self.bootloader = bootloader.BlsBootloader(self)

    def check(self):
        lvs = LVM._lvs(["--noheadings", "-odata_percent,metadata_percent",
                        self._thinpool().lvm_name])
        datap, metap = map(float, lvs.replace(",", ".").split())

        def thin_check():
            log.info("Checking available space in thinpool")
            fail = any(v > 80 for v in [datap, metap])
            if fail:
                log.warning("Data or Metadata usage is above threshold:")
                print(LVM._lvs([self._thinpool().lvm_name]))
            return fail

        def mount_check():
            log.info("Checking mount options of /")
            # FIXME we need to check mopts of correct path
            fail = "discard" not in sh.findmnt("-no", "options").split(",")
            if fail:
                log.warning("/ is not mounted with discard")
                print(sh.findmnt("/"))
            return fail

        def bls_check():
            fail = True
            try:
                sh.grep("bls_import", glob.glob("/etc/grub.d/*"))
                fail = False
            except:
                log.warning("BLS is not enabled in grub")
                print("echo 'echo bls_import' >> /etc/grub.d/05_bls")
                print("chmod a+x /etc/grub.d/05_bls")
            return fail

        checks = [thin_check, mount_check, bls_check]

        any_fail = False
        for check in checks:
            fail = check()
            any_fail = True if fail else False

        if any_fail:
            log.warn("There were warnings")
        else:
            log.info("The check completed without warnings")

    def _vg(self):
        vg = LVM.VG.from_tag(self.vg_tag)
        log.debug("VG candidate: %s" % vg)
        return vg

    def _thinpool(self):
        lv = LVM.LV.from_tag(self.thinpool_tag)
        log.debug("Thinpool candidate: %s" % lv)
        return lv

    def _lvs(self):
        log.debug("Querying for LVs")
        cmd = ["--noheadings", "-o", "lv_name"]
        raw = self.run.lvs(cmd)
        lvs = [n.strip() for n in raw.splitlines()]
        log.debug("Found lvs: %s" % lvs)
        return sorted(lvs)

    def _lvs_tree(self, lvs=None):
        return self.naming.tree()

    def image_from_name(self, name):
        return self.naming.image_from_name(name)

    def image_from_path(self, path):
        name = LVM.LV.from_path(path).lv_name
        log.info("Found LV '%s' for path '%s'" % (name, path))
        return self.image_from_name(name)

    def image_from_lvm_name(self, lvm_name):
        lv = LVM.LV.from_lvm_name(lvm_name)
        assert lv.vg_name == self._vg()
        return self.image_from_name(lv.lv_name)

    def layout(self, lvs=None):
        return self.naming.layout(lvs)

    def _add_layer(self, previous_layer, new_layer):
        """Add a new thin LV
        """
        log.info("Adding a new layer")
        previous_layer.create_snapshot(new_layer.lvm_name)

        try:
            # If an error is raised here, then:
            # https://bugzilla.redhat.com/show_bug.cgi?id=1227046
            # is not fixed yet.
            new_layer.activate(True, True)
        except:
            origin = new_layer.origin()
            log.debug("Found origin: %s" % origin)
            origin.activate(True, True)
            new_layer.activate(True, True)
            origin.activate(False)

        # Assign a new filesystem UUID and label
        self.run.tune2fs(["-U", "random",
                          "-L", new_layer.lv_name + "-fs",
                          new_layer.path])

        # Handle the previous layer
        # FIXME do a correct check if it's a base
        skip_if_is_base = previous_layer.lv_name.endswith(".0")
        previous_layer.setactivationskip(skip_if_is_base)

        skip_if_is_base = new_layer.lv_name.endswith(".0")
        new_layer.setactivationskip(skip_if_is_base)

    def _add_boot_entry(self, lv):
        """Add a new BLS based boot entry and update the layers /etc/fstab

        http://www.freedesktop.org/wiki/Specifications/BootLoaderSpec/
        """
        log.info("Adding a boot entry for the new layer")

        with mounted(lv.path) as mount:
            chroot = \
                sh.systemd_nspawn.bake("-q",
                                       "--bind", "/boot",
                                       "--bind", "%s:/image" % mount.target,
                                       "-D", mount.target)
            # kver = chroot("rpm", "-q", "kernel").strip().replace("kernel-",
            # "")
            kfiles = ["/image%s" % l for l in
                      chroot("rpm", "-ql", "kernel").splitlines()
                      if l.startswith("/boot")]
            print(kfiles)
            bootdir = "/boot/%s" % lv.lv_name
            chroot("mkdir", bootdir)
            cmd = ["cp", "-v"] + kfiles + [bootdir]
            # img = "/boot/%s/vmlinuz-%s" % (bootdir, kver)
            log.debug(chroot(*cmd))
            log.debug(chroot("passwd", "-d", "root"))

            fstab = "%s/etc/fstab" % mount.target
            if os.path.exists(fstab):
                log.info("Updating fstab of new layer")
                fstab = Fstab()
                rootentry = fstab.by_target("/")
                oldrootsource = rootentry.source
                rootentry.source = lv.path
                fstab.update(rootentry)

                defgrub = File("%s/etc/default/grub" % mount.target)
                if defgrub.exists():
                    oldrootlv = LVM.LV.try_find(oldrootsource)
                    # FIXME this is quite greedy
                    if oldrootlv.lvm_name in File(defgrub).contents:
                        log.info("Updating default/grub of new layer")
                        defgrub.replace(oldrootlv.lvm_name,
                                        lv.lvm_name)
                    else:
                        log.info("No defaults fiel found")
                else:
                    log.info("No grub foo found, not updating and not " +
                             "creating a boot entry.")

#                self.bootloader.add_boot_entry(lv.lvm_name, lv.path)
                osrelease = ShellVarFile(mount.target + "/etc/os-release")
                name = osrelease.parse()["PRETTY_NAME"]
                title = "%s (on %s)" % (name, lv.lvm_name)
                bfile = lambda n: [f for f in kfiles if n in f].pop()\
                    .replace("/image/boot", lv.lv_name)
                vmlinuz = bfile("vmlinuz")
                initrd = bfile("init")
                append = "rd.lvm.lv=%s root=/dev/%s" % (lv.lvm_name,
                                                        lv.lvm_name)
                self.bootloader._add_entry(title, vmlinuz, initrd, append)
            else:
                log.info("No fstab found, not updating and not creating a" +
                         "boot entry.")

    def init_layout_from(self, lvm_name_or_mount_target):
        """Create a snapshot from an existing thin LV to make it suitable
        """
        log.info("Trying to create a manageable base from '%s'" %
                 lvm_name_or_mount_target)
        if os.path.ismount(lvm_name_or_mount_target):
            lvm_path = find_mount_source(lvm_name_or_mount_target)
            existing = LVM.LV.from_path(lvm_path)
        else:
            # If it's not a mount point, then we assume it's a LVM name
            existing = LVM.LV.from_lvm_name(lvm_name_or_mount_target)
        log.debug("Found existing LV '%s'" % existing)
        log.debug("Tagging existing pool")
        LVM.VG(existing.vg_name).addtag(self.vg_tag)
        existing.thinpool().addtag(self.thinpool_tag)
        log.debug("Setting autoextend for thin pool, to prevent starvation")
        sh.augtool("set", "-s",
                   "/files/etc/lvm/lvm.conf/activation/dict/" +
                   "thin_pool_autoextend_threshold/int",
                   "80")
        today = int(datetime.date.today().strftime("%Y%m%d"))
        initial_base = self.naming.next_base(version=today).lvm
        log.info("Creating an initial base '%s' for '%s'" %
                 (initial_base, existing))
        self._add_layer(existing, initial_base)
        self.add_bootable_layer()

    def init_layout(self, pvs, poolsize):
        """Create the LVM layout needed by this tool
        """
        raise NotImplementedError
        assert poolsize > 0
        if pvs:
            LVM.VG.create(self.vg, pvs)
        LVM.VG(self._vg()).create_thinpool(self._thinpool(), poolsize)

    def add_bootable_layer(self):
        """Add a new layer which can be booted from the boot menu
        """
        log.info("Adding a new layer which can be booted from"
                 " the bootloader")
        try:
            last_layer = self.naming.last_layer()
            log.debug("Last layer: %s" % last_layer)
        except IndexError:
            last_layer = self.naming.last_base()
            log.debug("Last layer is a base: %s" % last_layer)
        new_layer = self.naming.next_layer()

        log.debug("New layer: %s" % last_layer)

        self._add_layer(last_layer.lvm, new_layer.lvm)
        self._add_boot_entry(new_layer.lvm)
        with mounted(new_layer.lvm.path) as mount:
            self.hooks.emit("new-layer-added", "/",
                            new_layer.lvm.path, mount.target)

    def add_base(self, size, version=None, lvs=None):
        """Add a new base LV
        """
        assert size

        new_base_lv = self.naming.next_base(version=version, lvs=lvs)
        log.debug("New base will be: %s" % new_base_lv)
        pool = LVM.Thinpool(self._vg(), self._thinpool().lv_name)
        pool.create_thinvol(new_base_lv.name, size)

        self.hooks.emit("new-base-added", new_base_lv.path)

        new_base_lv.protect()

        return new_base_lv

    def add_base_from_image(self, imagefile, size, version=None, lvs=None):
        new_base_lv = self.add_base(size, version, lvs)

        cmd = ["dd", "conv=sparse"]
        kwargs = {}

        if type(imagefile) is io.IOBase:
            log.debug("Reading base from stdin")
            kwargs["stdin"] = imagefile
        elif type(imagefile) in [str, bytes]:
            log.debug("Reading base from file: %s" % imagefile)
            cmd.append("if=%s" % imagefile)
        else:
            raise RuntimeError("Unknown infile: %s" % imagefile)

        cmd.append("of=%s" % new_base_lv.path)
        log.debug("Running: %s %s" % (cmd, kwargs))
        if not self.dry:
            subprocess.check_call(cmd, **kwargs)

    def add_base_with_tree(self, sourcetree, size, version=None, lvs=None):
        new_base_lv = self.add_base(size, version, lvs)

        if not os.path.exists(sourcetree):
            raise RuntimeError("Sourcetree does not exist: %s" % sourcetree)

        with new_base_lv.unprotected():
            mkfscmd = ["mkfs.ext4", "-c", "-E", "discard", new_base_lv.path]
            if not self.debug:
                mkfscmd.append("-q")
            log.debug("Running: %s" % mkfscmd)
            if not self.dry:
                pass
                subprocess.check_call(mkfscmd)

            with mounted(new_base_lv.path) as mount:
                dst = mount.target + "/"
                cmd = ["ionice"]
                cmd += ["rsync", "-pogAXtlHrDx", sourcetree + "/", dst]
                cmd += ["-Sc"]
                cmd += ["--info=progress2"]
                log.debug("Running: %s" % cmd)
                if not self.dry:
                    subprocess.check_call(cmd)

                self.hooks.emit("new-base-with-tree-added", dst)

    def free_space(self, units="m"):
        """Free space in the thinpool for bases and layers
        """
        log.debug("Calculating free space in thinpool %s" % self._thinpool())
        lvm_name = LVM.LV(self._vg(), self._thinpool()).lvm_name
        args = ["--noheadings", "--nosuffix", "--units", units,
                "--options", "data_percent,lv_size",
                lvm_name]
        stdout = LVM._lvs(args).replace(",", ".").strip()
        used_percent, size = re.split("\s+", stdout)
        log.debug("Used: %s%% from %s" % (used_percent, size))
        free = float(size)
        free -= float(size) * float(used_percent) / 100.00
        return free

    def latest_base(self):
        return self.naming.last_base()

    def latest_layer(self):
        return self.naming.last_layer()

    def current_layer(self):
        path = "/"
        log.info("Fetching image for '%s'" % path)
        lv = self.run.findmnt(["--noheadings", "-o", "SOURCE", path])
        log.info("Found '%s'" % lv)
        try:
            return self.image_from_path(lv)
        except:
            log.error("The root volume does not look like an image")
            raise

    def base_of_layer(self, layer):
        base = None
        args = ["--noheadings", "--options", "origin"]
        get_origin = lambda l: LVM._lvs(args +
                                        ["%s/%s" % (self._vg(), l)])

        while base is None and layer is not None:
            layer = get_origin(layer)
            if self.image_from_name(layer).is_base():
                base = layer

        if not base:
            raise RuntimeError("No base found for: %s" % layer)
        return base

# vim: sw=4 et sts=4

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
from .hooks import Hooks
from . import naming
from .utils import ExternalBinary, mounted, find_mount_source
from .lvm import LVM

import logging


log = logging.getLogger(__package__)


class ImageLayers(object):
    debug = False
    dry = False

    hooks = None

    vg_tag = "imgbased:vg"
    thinpool_tag = "imgbased:pool"
    lv_init_tag = "imgbased:init"
    lv_base_tag = "imgbased:base"
    lv_layer_tag = "imgbased:layer"

    run = None

    naming = None

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
                          ("previous-lv_fullname", "new-lv_fullname"))
        self.hooks.create("new-base-added",
                          ("new-lv_fullname",))
        self.hooks.create("new-base-with-tree-added",
                          ("new-fs",))

        self.run = ExternalBinary()
        self.naming = naming.NvrLikeNaming()
        self.naming.vg = self._vg
        self.naming.names = self._lvs

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

    def add_layer_on_latest(self):
        previous_layer = self.latest_layer()
        return self.add_layer(previous_layer)

    def add_layer_on_current(self):
        previous_layer = self.current_layer()
        return self.add_layer(previous_layer)

    def add_layer(self, previous_layer):
        """Add a new thin LV
        """
        log.info("Adding a new layer")

        log.debug("Basing new layer on previous: %s" % previous_layer)
        new_layer = self.naming.suggest_next_layer(previous_layer)
        log.info("New layer will be: %s" % new_layer)

        try:
            previous_layer.lvm.create_snapshot(new_layer.lvm.lvm_name)
            new_layer.lvm.addtag(self.lv_layer_tag)
        except:
            log.error("Failed to create a new layer")
            log.debug("Snapshot creation failed", exc_info=True)
            raise RuntimeError("Failed to create a new layer")

        try:
            # If an error is raised here, then:
            # https://bugzilla.redhat.com/show_bug.cgi?id=1227046
            # is not fixed yet.
            new_layer.lvm.activate(True, True)
        except:
            origin = new_layer.lvm.origin()
            log.debug("Found origin: %s" % origin)
            origin.activate(True, True)
            new_layer.lvm.activate(True, True)
            origin.activate(False)

        # Assign a new filesystem UUID and label
        self.run.tune2fs(["-U", "random",
                          "-L", new_layer.lvm.lv_name + "-fs",
                          new_layer.lvm.path])

        # Handle the previous layer
        # FIXME do a correct check if it's a base
        skip_if_is_base = previous_layer.lvm.lv_name.endswith(".0")
        previous_layer.lvm.setactivationskip(skip_if_is_base)

        skip_if_is_base = new_layer.lvm.lv_name.endswith(".0")
        new_layer.lvm.setactivationskip(skip_if_is_base)

        self.hooks.emit("new-layer-added",
                        previous_layer.lvm.lvm_name,
                        new_layer.lvm.lvm_name)

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
        existing.addtag(self.lv_init_tag)
        LVM.VG(existing.vg_name).addtag(self.vg_tag)
        existing.thinpool().addtag(self.thinpool_tag)
        log.debug("Setting autoextend for thin pool, to prevent starvation")
        sh.augtool("set", "-s",
                   "/files/etc/lvm/lvm.conf/activation/dict/" +
                   "thin_pool_autoextend_threshold/int",
                   "80")
        version = 0  # int(datetime.date.today().strftime("%Y%m%d"))
        initial_base = self.naming.suggest_next_base(version=version)
        log.info("Creating an initial base '%s' for '%s'" %
                 (initial_base, existing))
        self.add_layer(existing, initial_base.lvm)

    def init_layout(self, pvs, poolsize):
        """Create the LVM layout needed by this tool
        """
        raise NotImplementedError
        assert poolsize > 0
        if pvs:
            LVM.VG.create(self.vg, pvs)
        LVM.VG(self._vg()).create_thinpool(self._thinpool(), poolsize)

    def add_base(self, size, version=None, lvs=None):
        """Add a new base LV
        """
        assert size

        new_base_lv = self.naming.suggest_next_base(version=version)
        log.info("New base will be: %s" % new_base_lv)
        pool = LVM.Thinpool(self._vg(), self._thinpool().lv_name)
        pool.create_thinvol(new_base_lv.name, size)
        new_base_lv.lvm.addtag(self.lv_base_tag)

        self.hooks.emit("new-base-added", new_base_lv.path)

        new_base_lv.protect()

        return new_base_lv

    def add_base_from_image(self, imagefile, size, version=None, lvs=None):
        raise NotImplementedError
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

        return new_base_lv

    def add_base_with_tree(self, sourcetree, size, version=None, lvs=None):
        latest_layer = self.naming.images().pop()
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
                cmd += ["-Sc", "--no-i-r"]
                cmd += ["--info=progress2"]
                log.debug("Running: %s" % cmd)
                if not self.dry:
                    subprocess.check_call(cmd)
                    log.debug("Trying to copy prev fstab")
                    with mounted(latest_layer.path) as prev:
                        cpcmd = ["cp", "-v",
                                 prev.target + "/etc/fstab",
                                 dst + "/etc/fstab"]
                        self.run.call(cpcmd)
                        log.debug("Copied prev fstab")

                self.hooks.emit("new-base-with-tree-added", dst)

        return new_base_lv

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

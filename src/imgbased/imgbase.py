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
import os
import re
from .hooks import Hooks
from . import naming, utils
from .utils import find_mount_source, \
    augtool
from .lvm import LVM

import logging


log = logging.getLogger(__package__)


class LayerOutOfOrderError(Exception):
    pass


class ImageLayers(object):
    debug = False
    dry = False

    hooks = None
    hooksdir = "/usr/lib/imgbased/hooks.d/"

    stream_name = "Image"
    vg_tag = "imgbased:vg"
    thinpool_tag = "imgbased:pool"
    lv_init_tag = "imgbased:init"
    lv_base_tag = "imgbased:base"
    lv_layer_tag = "imgbased:layer"

    naming = None

    def __init__(self):
        self.hooks = Hooks(self)

        # A default wildcard hook is to also trigger
        # filesystem based hooks
        self.hooks.add_filesystem_emitter(self.hooksdir)

        #
        # Add availabel hooks
        #
        self.hooks.create("new-snapshot-added",
                          ("previous-lv_fullname", "new-lv_fullname"))
        self.hooks.create("new-layer-added",
                          ("previous-lv_fullname", "new-lv_fullname"))
        self.hooks.create("new-base-added",
                          ("new-lv_fullname",))
        self.hooks.create("new-base-with-tree-added",
                          ("new-fs",))
        self.hooks.create("pre-base-removed",
                          ("lv_fullname",))
        self.hooks.create("base-removed",
                          ("lv_fullname",))
        self.hooks.create("pre-layer-removed",
                          ("lv_fullname",))
        self.hooks.create("layer-removed",
                          ("lv_fullname",))

        # FIXME just pass tagged LVs
        self.naming = naming.NvrLikeNaming(datasource=LVM.list_lv_names)

    def _vg(self):
        return LVM.VG.from_tag(self.vg_tag)

    def _thinpool(self):
        return LVM.LV.from_tag(self.thinpool_tag)

    def _lvm_from_layer(self, layer):
        return LVM.LV.from_lv_name(self._vg().vg_name, layer.nvr)

    def image_from_name(self, name):
        return self.naming.image_from_name(name)

    def image_from_path(self, path):
        name = LVM.LV.from_path(path).lv_name
        log.debug("Found LV '%s' for path '%s'" % (name, path))
        return self.image_from_name(name)

    def image_from_lvm_name(self, lvm_name):
        lv = LVM.LV.from_lvm_name(lvm_name)
        assert lv.vg_name == self._vg()
        return self.image_from_name(lv.lv_name)

    def layout(self):
        return self.naming.layout()

    def add_layer_on_latest(self):
        previous_layer = self.latest_layer()
        log.debug("Planning to add layer onto %s" % previous_layer)
        if previous_layer < self.latest_base():
            raise LayerOutOfOrderError("Last layer is smaller than latest "
                                       "base. Are you missing a layer on the "
                                       "latest base?")
        return self.add_layer(previous_layer)

    def add_layer_on_current(self):
        previous_layer = self.current_layer()
        return self.add_layer(previous_layer)

    def add_layer(self, previous_layer):
        """Add a new thin LV
        """
        log.info("Adding a new layer after %s" % previous_layer)

        if type(previous_layer) in [str]:
            previous_layer = self.naming.image_from_name(previous_layer)

        log.debug("Basing new layer on previous: %s" % previous_layer)
        new_layer = self.naming.suggest_next_layer(previous_layer)
        log.info("New layer will be: %s" % new_layer)

        prev_lv = self._lvm_from_layer(previous_layer)

        new_lv = self._add_lvm_snapshot(prev_lv, new_layer.nvr)

        self.hooks.emit("new-layer-added", prev_lv, new_lv)

    def _add_lvm_snapshot(self, prev_lv, new_lv_name):
        try:
            # If an error is raised here, then:
            # https://bugzilla.redhat.com/show_bug.cgi?id=1227046
            # is not fixed yet.
            prev_lv.activate(True, True)

            new_lv = prev_lv.create_snapshot(new_lv_name)
            new_lv.activate(True, True)
            new_lv.addtag(self.lv_layer_tag)
        except:
            log.error("Failed to create a new layer")
            log.debug("Snapshot creation failed", exc_info=True)
            raise RuntimeError("Failed to create a new layer")

        # Assign a new filesystem UUID and label
        utils.Ext4.randomize_uuid(new_lv.path)

        # Handle the previous layer
        # FIXME do a correct check if it's a base
        skip_if_is_base = new_lv.lv_name.endswith(".0")
        new_lv.setactivationskip(skip_if_is_base)

        skip_if_is_base = prev_lv.lv_name.endswith(".0")
        prev_lv.setactivationskip(skip_if_is_base)

        self.hooks.emit("new-snapshot-added",
                        prev_lv,
                        new_lv)

        return new_lv

    def init_layout_from(self, lvm_name_or_mount_target):
        """Create a snapshot from an existing thin LV to make it suitable
        """
        log.info("Trying to create a manageable base from '%s'" %
                 lvm_name_or_mount_target)
        if os.path.ismount(lvm_name_or_mount_target):
            lvm_path = find_mount_source(lvm_name_or_mount_target)
            existing_lv = LVM.LV.from_path(lvm_path)
        else:
            # If it's not a mount point, then we assume it's a LVM name
            existing_lv = LVM.LV.from_lvm_name(lvm_name_or_mount_target)
        log.debug("Found existing LV '%s'" % existing_lv)

        log.debug("Tagging existing LV: %s" % existing_lv)
        existing_lv.addtag(self.lv_init_tag)

        existing_vg = LVM.VG.from_vg_name(existing_lv.vg_name)
        log.debug("Tagging existing VG: %s" % existing_vg)
        existing_vg.addtag(self.vg_tag)

        existing_pool = existing_lv.thinpool()
        log.debug("Tagging existing pool: %s" % existing_pool)
        existing_pool.addtag(self.thinpool_tag)

        # FIXME this should go into a plugin
        log.debug("Setting autoextend for thin pool, to prevent starvation")
        augtool("set", "-s",
                "/files/etc/lvm/lvm.conf/activation/dict/" +
                "thin_pool_autoextend_threshold/int",
                "80")

        version = 0  # int(datetime.date.today().strftime("%Y%m%d"))
        initial_base = self.naming.suggest_next_base(self.stream_name,
                                                     version, 0)
        new_layer = self.naming.suggest_next_layer(initial_base)
        log.info("Creating an initial base '%s' for '%s'" %
                 (initial_base, existing_lv))
        initial_base_lv = self._add_lvm_snapshot(existing_lv, initial_base.nvr)

        log.info("Creating initial layer for initial base")
        self._add_lvm_snapshot(initial_base_lv, new_layer.nvr)

    def add_base(self, size, nvr, lvs=None,
                 with_layer=False):
        """Add a new base LV
        """
        assert size

        base = self.naming.image_from_name(nvr)
        new_base = self.naming.suggest_next_base(base.name,
                                                 base.version,
                                                 base.release)

        log.info("New base will be: %s" % new_base)
        pool = self._thinpool()
        log.debug("Pool: %s" % pool)
        new_base_lv = pool.create_thinvol(new_base.nvr, size)
        new_base_lv.addtag(self.lv_base_tag)
        log.info("New LV is: %s" % new_base_lv)

        self.hooks.emit("new-base-added", new_base_lv.path)

        new_base_lv.protect()

        if with_layer:
            self.add_layer(new_base)

        return new_base_lv

    def remove_base(self, name, with_children=True):
        base = self.image_from_name(name)
        log.debug("Removal candidate: %s" % repr(base))

        base_lv = self._lvm_from_layer(base)
        self.hooks.emit("pre-base-removed", base_lv)

        assert base.is_base()

        if with_children:
            for layer in base.layers:
                self.remove_layer(layer.nvr)

        base_lv.activate(False)
        base_lv.remove()

        self.hooks.emit("base-removed", base_lv)

    def remove_layer(self, name):
        layer = self.image_from_name(name)
        lv = self._lvm_from_layer(layer)
        log.debug("Removal candidate: %s" % layer)

        self.hooks.emit("pre-layer-removed", lv)

        assert layer.is_layer()
        assert layer != self.current_layer()

        log.debug("Removing %s" % layer)
        lv.activate(False)
        lv.remove()

        self.hooks.emit("layer-removed", lv)

    def free_space(self, units="m"):
        """Free space in the thinpool for bases and layers
        """
        log.debug("Calculating free space in thinpool %s" % self._thinpool())
        lvm_name = LVM.LV.from_lv_name(self._vg(), self._thinpool()).lvm_name
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
        log.debug("Fetching image for '%s'" % path)
        lv = utils.source_of_mountpoint(path)
        log.debug("Found '%s'" % lv)
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
            base_candidate = self.image_from_name(layer)
            if base_candidate.is_base():
                base = base_candidate

        if not base:
            raise RuntimeError("No base found for: %s" % layer)
        return base

# vim: sw=4 et sts=4

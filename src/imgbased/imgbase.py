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
import re
from .hooks import Hooks
from . import naming, utils, local
from .naming import Image
from .lvm import LVM, MissingLvmThinPool

import logging

from utils import FilesystemNotSupported

log = logging.getLogger(__package__)


class LayerOutOfOrderError(Exception):
    pass


class ImageLayers(object):
    config = local.Configuration()

    debug = False
    dry = False

    hooks = None
    hooksdir = "/usr/lib/imgbased/hooks.d/"

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
        self.hooks.create("new-layer-added",
                          ("previous-lv_fullname", "new-lv_fullname"))
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
        self.hooks.create("post-init-layout",
                          ("existing_lv", "new_base", "new_layer"))

        self.naming = naming.NvrNaming(datasource=self.list_our_lv_names)

    def list_our_lv_names(self):
        lvs = LVM.list_lvs()

        def has_our_tag(lv):
            our_tags = [self.lv_base_tag, self.lv_layer_tag]
            return any(tag in lv.tags()
                       for tag in our_tags)

        our_lvs = [lv for lv in lvs if has_our_tag(lv)]
        log.debug("Our LVS: %s" % lvs)
        return [lv.lv_name for lv in our_lvs]

    def _vg(self):
        return LVM.VG.from_tag(self.vg_tag)

    def lv(self, lv_name):
        """Return an LV for an lv_name in the imgbase VG context
        """
        return LVM.LV.from_lv_name(self._vg().vg_name, lv_name)

    def _thinpool(self):
        return LVM.Thinpool.from_tag(self.thinpool_tag)

    def _lvm_from_layer(self, layer):
        return self.lv(layer.lv_name)

    def has_tags(self):
        try:
            self._vg()
        except AssertionError:
            return False
        for tag in [self.thinpool_tag, self.lv_init_tag]:
            try:
                LVM.LV.from_tag(tag)
            except AssertionError:
                raise RuntimeError("A tagged volume group was found, but no "
                                   "logical volumes were tagged with %s. "
                                   "Please remove tags from volume groups "
                                   "and logical volumes, then retry" % tag)
        return True

    def lv_from_layer(self, layer):
        return self._lvm_from_layer(layer)

    def image_from_path(self, path):
        name = LVM.LV.from_path(path).lv_name
        log.debug("Found LV '%s' for path '%s'" % (name, path))
        return Image.from_lv_name(name)

    def image_from_lvm_name(self, lvm_name):
        lv = LVM.LV.from_lvm_name(lvm_name)
        assert lv.vg_name == self._vg().vg_name
        return Image.from_lv_name(lv.lv_name)

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

    def add_layer(self, previous_layer, new_layer=None):
        """Add a new thin LV
        """
        log.info("Adding a new layer after %r" % previous_layer)

        if type(previous_layer) in [str, unicode, bytes]:
            previous_layer = Image.from_nvr(previous_layer)
        log.info("Adding a new layer after %r" % previous_layer)

        log.debug("Basing new layer on previous: %r" % previous_layer)
        new_layer = new_layer or self.naming.suggest_next_layer(previous_layer)
        log.info("New layer will be: %r" % new_layer)

        prev_lv = self._lvm_from_layer(previous_layer)

        try:
            new_lv = self._add_lvm_snapshot(prev_lv, new_layer.lv_name)
        except FilesystemNotSupported:
            log.error("Failed to add new layer! Filesystem not supported!")
            raise

        self.hooks.emit("new-layer-added", prev_lv, new_lv)

        return new_lv

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

        # Assign a new filesystem UUID
        try:
            utils.Filesystem.from_device(new_lv.path).randomize_uuid()
        except FilesystemNotSupported:
            log.error(
                "Filesystem not supported, please use: {0}".format(
                    ' '.join(utils.Filesystem.supported_filesystem())))
            raise

        # Handle the previous layer
        skip_if_is_base = Image.from_lv_name(new_lv.lv_name).is_base()
        new_lv.setactivationskip(skip_if_is_base)

        try:
            # It can happen (i.e. on init) that the prev_lv name
            # is not nvr based.
            skip_if_is_base = Image.from_lv_name(prev_lv.lv_name).is_base()
            prev_lv.setactivationskip(skip_if_is_base)
        except RuntimeError:
            log.debug("Failed to set activationskip on prev_lv", exc_info=True)

        return new_lv

    def init_tags_on(self, lv):
        lv = lv if type(lv) in [LVM.LV] else LVM.LV.try_find(lv)
        log.debug("Tagging LV: %s" % lv)
        lv.addtag(self.lv_init_tag)

        vg = LVM.VG.from_vg_name(lv.vg_name)
        log.debug("Tagging VG: %s" % vg)
        vg.addtag(self.vg_tag)

        try:
            pool = lv.thinpool()
        except MissingLvmThinPool:
            log.error(
                "LVM Thin Provisioning partitioning scheme is required.\n"
                "For autoinstall via Kickstart with LVM Thin Provisioning"
                " check options: --thinpool and --grow"
                "Please consult documentation for details\n"
            )
            raise

        log.debug("Tagging pool: %s" % pool)
        pool.addtag(self.thinpool_tag)

    def init_layout_from(self, lvm_name_or_mount_target, initial_nvr):
        """Create a snapshot from an existing thin LV to make it suitable
        """
        if self.has_tags():
            raise RuntimeError("An existing imgbase was found with tags, but "
                               "imgbase was called with --init. If this was"
                               "intentional, please untag the existing "
                               "volumes and try again.")
        log.info("Trying to create a manageable base from '%s'" %
                 lvm_name_or_mount_target)
        existing_lv = LVM.LV.try_find(lvm_name_or_mount_target)
        self.init_tags_on(existing_lv)

        initial_base = Image.from_nvr(initial_nvr)
        log.info("Initial base will be %r" % initial_base)

        new_layer = self.naming.suggest_next_layer(initial_base)
        log.info("Initial layer will be %r" % new_layer)

        log.info("Creating an initial base %r for %r" %
                 (initial_base, existing_lv))

        try:
            self._add_lvm_snapshot(existing_lv,
                                   initial_base.lv_name)
        except FilesystemNotSupported:
            log.error(
                "Failed to create initial layout! Filesystem not supported!"
            )
            raise

        log.info("Creating initial layer %r for initial base" % new_layer)
        self.add_layer(initial_base, new_layer)

        self.hooks.emit("post-init-layout",
                        existing_lv, initial_base, new_layer)

    def add_base(self, size, nvr, lvs=None,
                 with_layer=False):
        """Add a new base LV
        """
        assert size

        new_base = Image.from_nvr(nvr)
        log.info("New base will be: %s" % new_base)

        pool = self._thinpool()
        log.debug("Pool: %s" % pool)

        new_base_lv = pool.create_thinvol(new_base.lv_name, size)
        new_base_lv.addtag(self.lv_base_tag)
        log.info("New LV is: %s" % new_base_lv)

        new_base_lv.protect()

        if with_layer:
            self.add_layer(new_base)

        return new_base

    def remove_base(self, name, with_children=True):
        base = Image.from_nvr(name)
        log.debug("Removal candidate base: %r" % base)

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
        layer = Image.from_nvr(name)
        lv = self._lvm_from_layer(layer)
        log.debug("Removal candidate layer: %r" % layer)

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
        lvm_name = self._thinpool().lvm_name
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
        return Image.from_nvr(layer).base

# vim: sw=4 et sts=4

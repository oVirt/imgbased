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
import subprocess
import re
from .hooks import Hooks
from . import bootloader
from .utils import memoize, ExternalBinary, format_to_pattern, \
    mounted


def log():
    return logging.getLogger()


class ImageLayers(object):
    debug = False
    dry = False

    hooks = None

    vg = "HostVG"
    thinpool = "ImagePool"
    layerformat = "Image-%d.%d"

    run = None

    bootloader = None

    class Image(object):
        p = None
        version = None
        release = None
        layers = None

        @property
        def name(self):
            return str(self)

        @property
        @memoize
        def path(self):
            return self.p.run.lvs(["--noheadings", "-olv_path",
                                   "%s/%s" % (self.p.vg, self.name)])

        def __init__(self, p, v=None, r=None):
            self.p = p
            self.version = v
            self.release = r
            self.layers = []

        def __str__(self):
            return self.p.layerformat % (self.version, self.release)

        def __repr__(self):
            return "<%s %s/>" % (self, self.layers or "")

        def is_base(self):
            return self.release == 0

        def is_layer(self):
            return not self.is_base()

    def __init__(self):
        self.hooks = Hooks(self)
        self.hooks.create("new-layer-added",
                          ("old-target", "new-lv", "new-target"))
        self.hooks.create("new-base-added",
                          ("new-lv",))
        self.run = ExternalBinary()
        self.bootloader = bootloader.BlsBootloader(self)

    def _lvs(self):
        log().debug("Querying for LVs")
        cmd = ["--noheadings", "-o", "lv_name"]
        lvs = [n.strip() for n in self.run.lvs(cmd).split("\n")]
        log().debug("Found lvs: %s" % lvs)
        return sorted(lvs)

    def _lvs_tree(self, lvs=None):
        """
        >>> layers = ImageLayers()

        >>> lvs = []
        >>> layers._lvs_tree(lvs)
        Traceback (most recent call last):
        ...
        RuntimeError: No bases found: []

        >>> lvs = ["Image-0.0", "Image-13.0", "Image-2.1", "Image-2.0"]
        >>> layers._lvs_tree(lvs)
        [<Image-0.0 />, <Image-2.0 [<Image-2.1 />]/>, <Image-13.0 />]
        """
        laypat = format_to_pattern(self.layerformat)
        sorted_lvs = []

        if lvs is None:
            lvs = self._lvs()

        for lv in lvs:
            if not re.match(laypat, lv):
                continue
            baseidx, layidx = [int(x) for x in re.search(laypat, lv).groups()]
            sorted_lvs.append((baseidx, layidx))

        sorted_lvs = sorted(sorted_lvs)

        lst = []
        imgs = (ImageLayers.Image(self, *v) for v in sorted_lvs)
        for img in imgs:
            if img.release == 0:
                lst.append(img)
            else:
                lst[-1].layers.append(img)

        if len(lst) == 0:
            raise RuntimeError("No bases found: %s" % lvs)

        return lst

    def image_from_name(self, name):
        laypat = format_to_pattern(self.layerformat)
        log().info("Fetching %s from %s" % (laypat, name))
        match = re.search(laypat, name)
        if not match:
            raise RuntimeError("Failed to parse image name: %s" % name)
        version, release = match.groups()
        return ImageLayers.Image(self, int(version), int(release))

    def layout(self, lvs=None):
        """List all bases and layers for humans

        >>> layers = ImageLayers()

        >>> lvs = []
        >>> print(layers.layout(lvs))
        Traceback (most recent call last):
        ...
        RuntimeError: No valid layout found. Initialize if needed.

        >>> lvs = ["Image-0.0", "Image-13.0", "Image-2.1", "Image-2.0"]
        >>> lvs += ["Image-2.2"]
        >>> print(layers.layout(lvs))
        Image-0.0
        Image-2.0
         ├╼ Image-2.1
         └╼ Image-2.2
        Image-13.0
        """
        idx = []
        try:
            tree = self._lvs_tree(lvs)
        except RuntimeError:
            raise RuntimeError("No valid layout found. Initialize if needed.")

        for base in tree:
            idx.append("%s" % base.name)
            for layer in base.layers:
                c = "└" if layer is base.layers[-1] else "├"
                idx.append(" %s╼ %s" % (c, layer.name))
        return "\n".join(idx)

    def _last_base(self, lvs=None):
        """Determine the last base LV name

        >>> layers = ImageLayers()

        >>> layers._last_base([])
        Traceback (most recent call last):
        ...
        RuntimeError: No bases found: []

        >>> lvs = ["Image-0.0", "Image-13.0", "Image-2.1", "Image-2.0"]
        >>> layers._last_base(lvs)
        <Image-13.0 />
        """
        return self._lvs_tree(lvs)[-1]

    def _next_base(self, version=None, lvs=None):
        """Dertermine the name for the next base LV name (based on the scheme)

        >>> layers = ImageLayers()

        >>> layers._next_base(lvs=[])
        <Image-0.0 />

        >>> lvs = ["Image-0.0"]
        >>> layers._next_base(lvs=lvs)
        <Image-1.0 />

        >>> lvs = ["Image-0.0", "Image-13.0", "Image-13.1", "Image-2.0"]
        >>> layers._next_base(lvs=lvs)
        <Image-14.0 />

        >>> layers._next_base(version=20140401, lvs=lvs)
        <Image-20140401.0 />
        """
        try:
            base = self._last_base(lvs)
            base.version = version or int(base.version) + 1
            base.release = 0
            base.layers = []
        except RuntimeError:
            base = ImageLayers.Image(self, version or 0, 0)
        return base

    def _last_layer(self, base=None, lvs=None):
        """Determine the LV name of the last layer of a base

        >>> layers = ImageLayers()

        >>> lvs = []
        >>> layers._last_layer(lvs=lvs)
        Traceback (most recent call last):
        ...
        RuntimeError: No bases found: []

        >>> lvs = ["Image-0.0", "Image-13.0", "Image-13.1", "Image-2.0"]
        >>> layers._last_layer(lvs=lvs)
        <Image-13.1 />
        """
        base = base or self._last_base(lvs)
        images = dict((x.name, x) for x in self._lvs_tree(lvs))
        return images[base.name].layers[-1]

    def _next_layer(self, base=None, lvs=None):
        """Determine the LV name of the next layer (based on the scheme)

        >>> layers = ImageLayers()

        >>> lvs = ["Image-0.0"]
        >>> layers._next_layer(lvs=lvs)
        <Image-0.1 />

        >>> lvs = ["Image-0.0", "Image-13.0", "Image-13.1", "Image-2.0"]
        >>> layers._next_layer(lvs=lvs)
        <Image-13.2 />
        """
        try:
            layer = self._last_layer(base, lvs)
            layer.release = int(layer.release) + 1
            layer.layers = []
        except IndexError:
            base = self._last_base(lvs)
            layer = ImageLayers.Image(self, base.version, 1)
        return layer

    def _add_layer(self, previous_layer, new_layer):
        """Add a new thin LV
        """
        log().info("Adding a new layer")
        self.run.lvcreate(["--snapshot", "--name", new_layer,
                           previous_layer])
        self.run.lvchange(["--activate", "y",
                           "--setactivationskip", "n", previous_layer])
        self.run.lvchange(["--activate", "y",
                           "--setactivationskip", "n", new_layer])

    def _add_boot_entry(self, name, rootlv):
        """Add a new BLS based boot entry and update the layers /etc/fstab

        http://www.freedesktop.org/wiki/Specifications/BootLoaderSpec/
        """
        log().info("Adding a boot entry for the new layer")

        self.bootloader.add_boot_entry(name, rootlv)

        with mounted(rootlv) as mount:
            log().info("Updating fstab of new layer")
            self.run.call(["sed", "-i", r"/[ \t]\/[ \t]/ s#^[^ \t]\+#%s#" %
                           rootlv, "%s/etc/fstab" % mount.target])
            self.hooks.emit("new-layer-added", "/", rootlv, mount.target)

    def init_layout(self, pvs, poolsize, without_vg=False):
        """Create the LVM layout needed by this tool
        """
        assert (not without_vg and pvs) or (without_vg)
        assert poolsize > 0
        if not without_vg:
            self.run.vgcreate([self.vg] + pvs)
        self._create_thinpool(poolsize)

    def _create_thinpool(self, poolsize):
        assert poolsize > 0
        self.run.lvcreate(["--size", str(poolsize),
                           "--thin", "%s/%s" % (self.vg, self.thinpool)])

    def _create_thinvol(self, name, volsize):
        self.run.lvcreate(["--name", name,
                           "--virtualsize", str(volsize),
                           "--thin", "%s/%s" % (self.vg, self.thinpool)])

    def add_bootable_layer(self):
        """Add a new layer which can be booted from the boot menu
        """
        log().info("Adding a new layer which can be booted from"
                   " the bootloader")
        try:
            last_layer = self._last_layer()
            log().debug("Last layer: %s" % last_layer)
        except IndexError:
            last_layer = self._last_base()
            log().debug("Last layer is a base: %s" % last_layer)
        new_layer = self._next_layer()

        log().debug("New layer: %s" % last_layer)

        self._add_layer("%s/%s" % (self.vg, last_layer.name),
                        "%s/%s" % (self.vg, new_layer.name))
        self._add_boot_entry("%s/%s" % (self.vg, new_layer),
                             new_layer.path)

    def add_base(self, infile, size, version=None, lvs=None):
        """Add a new base LV
        """
        assert infile
        assert size > 0

        cmd = ["dd", "conv=sparse"]
        kwargs = {}

        if type(infile) is file:
            log().debug("Reading base from stdin")
            kwargs["stdin"] = infile
        elif type(infile) in [str, unicode]:
            log().debug("Reading base from file: %s" % infile)
            cmd.append("if=%s" % infile)
        else:
            raise RuntimeError("Unknown infile: %s" % infile)

        new_base_lv = self._next_base(version=version, lvs=lvs)
        log().debug("New base will be: %s" % new_base_lv)
        self._create_thinvol(new_base_lv.name, size)

        cmd.append("of=%s" % new_base_lv.path)
        log().debug("Running: %s %s" % (cmd, kwargs))
        if not self.dry:
            subprocess.check_call(cmd, **kwargs)

        self.run.lvchange(["--permission", "r",
                           "%s/%s" % (self.vg, new_base_lv.name)])

        self.hooks.emit("new-base-added", new_base_lv.path)

    def free_space(self, units="m"):
        """Free space in the thinpool for bases and layers
        """
        log().debug("Calculating free space in thinpool %s" % self.thinpool)
        args = ["--noheadings", "--nosuffix", "--units", units,
                "--options", "data_percent,lv_size",
                "%s/%s" % (self.vg, self.thinpool)]
        stdout = self.run.lvs(args).replace(",", ".").strip()
        used_percent, size = re.split("\s+", stdout)
        log().debug("Used: %s%% from %s" % (used_percent, size))
        free = float(size)
        free -= float(size) * float(used_percent) / 100.00
        return free

    def latest_base(self):
        return self._last_base()

    def latest_layer(self):
        return self._last_layer()

    def base_of_layer(self, layer):
        base = None
        args = ["--noheadings", "--options", "origin"]
        get_origin = lambda l: self.run.lvs(args +
                                            ["%s/%s" % (self.vg, l)])

        while base is None and layer is not None:
            layer = get_origin(layer)
            if self.image_from_name(layer).is_base():
                base = layer

        if not base:
            raise RuntimeError("No base found for: %s" % layer)
        return base

    def verify(self, base):
        """Verify that a base has not been changed
        """
        raise NotImplemented()

# vim: sw=4 et sts=4

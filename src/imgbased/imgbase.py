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
import os
import glob
import subprocess
import re
import tempfile
import functools
import difflib
from .hooks import Hooks


def log():
    return logging.getLogger()


def memoize(obj):
    cache = obj.cache = {}

    @functools.wraps(obj)
    def memoizer(*args, **kwargs):
        key = str(args) + str(kwargs)
        if key not in cache:
            cache[key] = obj(*args, **kwargs)
        return cache[key]
    return memoizer


def call(*args, **kwargs):
    kwargs["close_fds"] = True
    log().debug("Calling: %s %s" % (args, kwargs))
    return subprocess.check_output(*args, **kwargs).strip()


def uuid():
    with open("/proc/sys/kernel/random/uuid") as src:
        return src.read().replace("-", "").strip()


def format_to_pattern(fmt):
    """Take a format string and make a pattern from it
    https://docs.python.org/2/library/re.html#simulating-scanf

    >>> fmt = "Bar-%d"
    >>> pat = format_to_pattern(fmt)
    >>> pat
    'Bar-([-+]?\\\\d+)'

    >>> re.search(pat, "Bar-01").groups()
    ('01',)
    """
    pat = fmt
    pat = pat.replace("%d", r"([-+]?\d+)")
    pat = pat.replace("%s", r"(\S+)")
    return pat


class mounted(object):
    source = None
    options = None
    _target = None

    run = None
    tmpdir = None

    @property
    def target(self):
        return self._target or self.tmpdir

    def __init__(self, source, options=None, target=None):
        self.run = ExternalBinary()
        self.source = source
        self.options = options
        self._target = target

    def __enter__(self):
        options = "-o%s" % self.options if self.options else None
        self.tmpdir = self._target or \
            self.run.call(["mktemp", "-d", "--tmpdir", "mnt.XXXXX"])

        if not os.path.exists(self.tmpdir):
            self.run.call(["mkdir", "-p", self.tmpdir])

        cmd = ["mount"]
        if options:
            cmd.append(options)
        cmd += [self.source, self.tmpdir]
        self.run.call(cmd)

        return self

    def __exit__(self, exc_type, exc_value, tb):
        self.run.call(["umount", self.source])
        if not self._target:
            self.run.call(["rmdir", self.tmpdir])


class ExternalBinary(object):
    dry = False

    def call(self, *args, **kwargs):
        log().debug("Calling: %s %s" % (args, kwargs))
        stdout = ""
        if not self.dry:
            stdout = call(*args, **kwargs)
            log().debug("Returned: %s" % stdout[0:1024])
        return stdout.strip()

    def lvs(self, args, **kwargs):
        return self.call(["lvs"] + args, **kwargs)

    def lvcreate(self, args, **kwargs):
        return self.call(["lvcreate"] + args, **kwargs)

    def vgcreate(self, args, **kwargs):
        return self.call(["vgcreate"] + args, **kwargs)

    def lvchange(self, args, **kwargs):
        return self.call(["lvchange"] + args, **kwargs)

    def find(self, args, **kwargs):
        return self.call(["find"] + args, **kwargs)


class Bootloader(object):
    """Fixme can probably use new-kernel-pkg
    """
    p = None
    bls_dir = "/boot/loader/entries"

    def __init__(self, p):
        self.p = p

    def add_boot_entry(self, name, rootlv):
        eid = uuid()
        edir = self.bls_dir

        if not os.path.isdir(edir):
            os.makedirs(edir)

        efile = os.path.join(edir, "%s.conf" % eid)

        def grep_boot(pat):
            # sorted: Just the last/highest entry
            highest = sorted(glob.glob("/boot/%s" % pat))[-1]
            # Just the filename
            return os.path.basename(highest)

        linux = grep_boot("vmlinuz-*.x86_64")
        initramfs = grep_boot("initramfs-*.x86_64.img")

        entry = ["title %s" % name,
                 "linux /%s" % linux,
                 "initrd /%s" % initramfs,
                 "options rd.lvm.lv=%s root=%s console=ttyS0" % (name, rootlv)]

        log().debug("Entry: %s" % entry)
        if not self.p.dry:
            with open(efile, "w+") as dst:
                dst.write("\n".join(entry))


class ImageLayers(object):
    debug = False
    dry = False

    hooks = None

    vg = "HostVG"
    thinpool = "ImagePool"
    layerformat = "Image-%d.%d"

    run = None

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

        >>> lvs = []
        >>> layers._last_base(lvs)
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

        >>> lvs = []
        >>> layers._next_base(lvs=lvs)
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

        Bootloader(self).add_boot_entry(name, rootlv)

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

    def diff(self, left, right, mode="tree"):
        """

        Args:
            left: Base or layer
            right: Base or layer
            mode: tree, content, unified
        """
        log().info("Diff '%s' between '%s' and '%s'" % (left, right, mode))

        imgl = self.image_from_name(left)
        imgr = self.image_from_name(right)

        with mounted(imgl.path) as mountl, \
                mounted(imgr.path) as mountr:
            if mode == "tree":
                l = self.run.find(["-ls"], cwd=mountl.target).splitlines(True)
                r = self.run.find(["-ls"], cwd=mountr.target).splitlines(True)
                udiff = difflib.unified_diff(r, l, fromfile=left, tofile=right, n=0)
                return (l for l in udiff if not l.startswith("@"))
            else:
                raise RuntimeError("Unknown diff mode: %s" % mode)

    def verify(self, base):
        """Verify that a base has not been changed
        """
        raise NotImplemented()

    def nspawn(self, layer, cmd=""):
        """Spawn a container off the root of layer layer
        """
        log().info("Adding a boot entry for the new layer")

        img = self.image_from_name(layer)
        with mounted(img.path) as mount:
            log().info("Changing root into layer %s" % img)
            cmds = [cmd] if cmd else []
            subprocess.call(["systemd-nspawn", "-D", mount.target,
                             "-M", layer, "--read-only"] + cmds)
# vim: sw=4 et

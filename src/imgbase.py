#! /usr/bin/python
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
log = logging.getLogger("imgbase")
import argparse
import os
import glob
import subprocess
import re
import sys


def call(*args, **kwargs):
    kwargs["close_fds"] = True
#    log.debug("Calling: %s %s" % (args, kwargs))
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


class Bin(object):
    dry = False
    def call(self, *args, **kwargs):
        log.debug("Calling: %s %s" % (args, kwargs))
        stdout = ""
        if not self.dry:
            stdout = call(*args, **kwargs)
            log.debug("Returned: %s" % stdout)
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

    def diff(self, args, **kwargs):
        return self.call(["diff"] + args, **kwargs)


class Hooks(object):
    p = None
    hooksdir = "/usr/lib/imgbased/hooks.d/"
    hooks = None

    def __init__(self, p):
        self.p = p
        self.hooks = {}

    def connect(self, name, cb):
        self.hooks.setdefault(name, set()).add(cb)

    def trigger(self, name, *args):
        self._trigger_fs(name, *args)
        self._trigger(name, *args)

    def _trigger(self, name, *args):
        for cb in self.hooks.get(name, set()):
            log.debug("Triggering: %s (%s)" % (cb, args))
            cb(*args)

    def _trigger_fs(self, name, *args):
        if not os.path.exists(self.hooksdir):
            return
        for handler in os.listdir(self.hooksdir):
            script = os.path.join(self.hooksdir, handler)
            log.debug("Triggering: %s (%s)" % (script, args))
            self.p.run.call([script] + list(args))


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
            return sorted(glob.glob("/boot/%s" % pat))[-1]

        linux = grep_boot("vmlinuz-*.x86_64")
        initramfs = grep_boot("initramfs-*.x86_64.img")

        entry = ["title %s" % name,
                 "linux %s" % linux,
                 "initrd %s" % initramfs,
                 "options rd.lvm.lv=%s root=%s console=ttyS0" % (name, rootlv)]

        log.debug("Entry: %s" % entry)
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

    def __init__(self):
        self.hooks = Hooks(self)
        self.run = Bin()

    def _lvs(self):
        log.debug("Querying for LVs")
        cmd = ["--noheadings", "-o", "lv_name"]
        lvs = [n.strip() for n in self.run.lvs(cmd).split("\n")]
        log.debug("Found lvs: %s" % lvs)
        return sorted(lvs)

    def _lvs_tree(self, lvs=None):
        """
        >>> layers = ImageLayers()

        >>> lvs = []
        >>> layers._lvs_tree(lvs)
        []

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

        return lst

    def layout(self, lvs=None):
        """List all bases and layers for humans

        >>> layers = ImageLayers()

        >>> lvs = []
        >>> print(layers.layout(lvs))
        Traceback (most recent call last):
        ...
        RuntimeError: No valid layout found. Initialize if needed.

        >>> lvs = ["Image-0.0", "Image-13.0", "Image-2.1", "Image-2.0"]
        >>> print(layers.layout(lvs))
        Image-0.0
        Image-2.0
          Image-2.1
        Image-13.0
        """
        idx = []
        for base in self._lvs_tree(lvs):
            idx.append("%s" % base.name)
            for layer in base.layers:
                idx.append("  %s" % layer.name)
        if not idx:
            raise RuntimeError("No valid layout found. Initialize if needed.")
        return "\n".join(idx)

    def _last_base(self, lvs=None):
        """Determine the last base LV name

        >>> layers = ImageLayers()

        >>> lvs = []
        >>> layers._last_base(lvs)
        Traceback (most recent call last):
        ...
        IndexError: list index out of range

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
        except IndexError:
            base = ImageLayers.Image(self, version or 0, 0)
        return base

    def _last_layer(self, base=None, lvs=None):
        """Determine the LV name of the last layer of a base

        >>> layers = ImageLayers()

        >>> lvs = []
        >>> layers._last_layer(lvs=lvs)
        Traceback (most recent call last):
        ...
        IndexError: list index out of range

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
        log.info("Adding a new layer")
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
        log.info("Adding a boot entry for the new layer")

        Bootloader(self).add_boot_entry(name, rootlv)

        tmpdir = self.run.call(["mktemp", "-d"])
        self.run.call(["mkdir", "-p", tmpdir])
        self.run.call(["mount", rootlv, tmpdir])
        log.info("Updating fstab of new layer")
        self.run.call(["sed", "-i", r"/[ \t]\/[ \t]/ s#^[^ \t]\+#%s#" % rootlv,
                       "%s/etc/fstab" % tmpdir])
        self.hooks.trigger("new-layer-added", "/", tmpdir)
        self.run.call(["umount", rootlv])
        self.run.call(["rmdir", tmpdir])

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
        self.run.lvcreate(["--size", "%sM" % poolsize,
                           "--thin", "%s/%s" % (self.vg, self.thinpool)])

    def _create_thinvol(self, name, volsize):
        self.run.lvcreate(["--name", name,
                           "--virtualsize", str(volsize),
                           "--thin", "%s/%s" % (self.vg, self.thinpool)])

    def add_bootable_layer(self):
        """Add a new layer which can be booted from the boot menu
        """
        log.info("Adding a new layer which can be booted from the bootloader")
        try:
            last_layer = self._last_layer()
            log.debug("Last layer: %s" % last_layer)
        except IndexError:
            last_layer = self._last_base()
            log.debug("Last layer is a base: %s" % last_layer)
        new_layer = self._next_layer()

        log.debug("New layer: %s" % last_layer)

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
            log.debug("Reading base from stdin")
            kwargs["stdin"] = infile
        elif type(infile) in [str, unicode]:
            log.debug("Reading base from file: %s" % infile)
            cmd.append("if=%s" % infile)
        else:
            raise RuntimeError("Unknown infile: %s" % infile)

        new_base_lv = self._next_base(version=version, lvs=lvs)
        log.debug("New base will be: %s" % new_base_lv)
        cmd.append("of=%s" % new_base_lv.path)

        self._create_thinvol(new_base_lv, size)

        self.debug("Running: %s %s" % (cmd, kwargs))
        if not self.dry:
            subprocess.check_call(cmd, **kwargs)

        self.run.lvchange(["--permission", "r"])

        self.hooks.trigger("new-base-added", new_base_lv.name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="imgbased")
    subparsers = parser.add_subparsers(title="Sub-commands", dest="command")

    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--dry", action="store_true")
    parser.add_argument("--vg", help="Volume Group to use",
                        default=ImageLayers.vg)
    parser.add_argument("--thinpool", help="Thinpool to use",
                        default=ImageLayers.thinpool)
    parser.add_argument("--layerformat", help="Format to discover layers",
                        default=ImageLayers.layerformat)

    layout_parser = subparsers.add_parser("layout",
                                          help="List all bases and layers")
    init_group = layout_parser.add_argument_group("Initialization arguments")
    init_group.add_argument("--init", action="store_true", default=False,
                            help="Create the initial Volume Group")
    init_group.add_argument("--size", type=int,
                            help="Size of the thinpool (in MB)")
    init_group.add_argument("pv", nargs="*", metavar="PV", type=file,
                            help="LVM PVs to use")
    init_group.add_argument("--without-vg", action="store_true", default=False,
                            help="If a Volume Group shall be created")

    base_parser = subparsers.add_parser("base",
                                        help="Runtime base handling")
    base_parser.add_argument("--add", action="store_true",
                             help="Add a base layer from a file or stdin")
    base_parser.add_argument("--size", type=int,
                             help="(Virtual) Size of the thin volume")
    base_parser.add_argument("image", nargs="?", type=argparse.FileType('r'),
                             default=sys.stdin,
                             help="File or stdin to use")

    layer_parser = subparsers.add_parser("layer",
                                         help="Runtime layer handling")
    layer_parser.add_argument("--add", action="store_true",
                              default=False, help="Add a new layer")

    args = parser.parse_args()

    lvl = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=lvl)

    log.debug("Arguments: %s" % args)

    #
    # Get started
    #
    imgbase = ImageLayers()
    imgbase.vg = args.vg
    imgbase.thinpool = args.thinpool
    imgbase.layerformat = args.layerformat
    imgbase.debug = args.debug
    imgbase.dry = args.dry

    if args.command == "layout":
        if args.init:
            if not args.size or not args.pv:
                raise RuntimeError("--size and PVs required")
            imgbase.init_layout(args.pv, args.size, args.without_vg)
        else:
            print(imgbase.layout())

    elif args.command == "layer":
        if args.add:
            imgbase.add_bootable_layer()

    elif args.command == "base":
        if args.add:
            if not args.size or not args.image:
                raise RuntimeError("--size and image required")
            imgbase.add_base(args.image, args.size)

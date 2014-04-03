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
logging.basicConfig(level=logging.DEBUG)
import argparse
import os
import glob
import subprocess
import re
import sys


def call(*args, **kwargs):
    kwargs["close_fds"] = True
#    log.debug("Calling: %s %s" % (args, kwargs))
    return subprocess.check_output(*args, **kwargs)


def uuid():
    with open("/proc/sys/kernel/random/uuid") as src:
        return src.read().replace("-", "")


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


class Hooks(object):
    hooksdir = "/usr/lib/imgbased/hooks.d/"
    hooks = None

    def __init__(self):
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
            self.call([script] + args)


class ImageLayers(object):
    debug = False
    dry = False

    bls_dir = "/boot/loader/entries"
    hooks = None

    vg = "HostVG"
    thinpool = "ImagePool"
    layerformat = "Image-%d.%d"

    class Image(object):
        version = None
        release = None
        layers = None

        @property
        def name(self):
            return str(self)

        def __init__(self, v=None, r=None):
            self.version = v
            self.release = r
            self.layers = []

        def __str__(self):
            return ImageLayers.layerformat % (self.version, self.release)

        def __repr__(self):
            return "<%s %s/>" % (self, self.layers or "")

    def __init__(self):
        self.hooks = Hooks()

    def call(self, *args, **kwargs):
        log.debug("Calling: %s %s" % (args, kwargs))
        if not self.dry:
            return call(*args, **kwargs)

    def _lvs(self):
        return sorted(n.strip() for n in
                      call(["lvs", "--noheadings", "-o", "lv_name"]))

    def _lvs_tree(self, lvs=None):
        """
        >>> lvs = ["Image-0.0", "Image-13.0", "Image-2.1", "Image-2.0"]

        >>> layers = ImageLayers()
        >>> layers._lvs_tree(lvs)
        [<Image-0.0 />, <Image-2.0 [<Image-2.1 />]/>, <Image-13.0 />]
        """
        laypat = format_to_pattern(self.layerformat)
        sorted_lvs = []

        lvs = lvs or self._lvs()

        for lv in lvs:
            if not re.match(laypat, lv):
                continue
            baseidx, layidx = [int(x) for x in re.search(laypat, lv).groups()]
            sorted_lvs.append((baseidx, layidx))

        sorted_lvs = sorted(sorted_lvs)

        lst = []
        for img in (ImageLayers.Image(*v) for v in sorted_lvs):
            if img.release == 0:
                lst.append(img)
            else:
                lst[-1].layers.append(img)

        return lst

    def _last_base(self, lvs=None):
        """
        >>> lvs = ["Image-0.0", "Image-13.0", "Image-2.1", "Image-2.0"]

        >>> layers = ImageLayers()
        >>> layers._last_base(lvs)
        <Image-13.0 />
        """
        return self._lvs_tree(lvs)[-1]

    def _last_layer(self, base=None, lvs=None):
        """
        >>> lvs = ["Image-0.0", "Image-13.0", "Image-13.1", "Image-2.0"]

        >>> layers = ImageLayers()
        >>> layers._last_layer(lvs=lvs)
        <Image-13.1 />
        """
        base = base or self._last_base(lvs)
        images = dict((x.name, x) for x in self._lvs_tree(lvs))
        return images[base.name].layers[-1]

    def _next_layer(self, base=None, lvs=None):
        """
        >>> lvs = ["Image-0.0", "Image-13.0", "Image-13.1", "Image-2.0"]

        >>> layers = ImageLayers()
        >>> layers._next_layer(lvs=lvs)
        <Image-13.2 />
        """
        last_layer = self._last_layer(base, lvs)
        last_layer.release += 1
        return last_layer

    def _add_layer(self, previous_layer, new_layer):
        log.info("Adding a new layer")
        self.call(["lvcreate", "--snapshot", "--name", new_layer,
                   previous_layer])
        self.call(["lvchange", "--activate", "y",
                   "--setactivationskip", "n", previous_layer])
        self.call(["lvchange", "--activate", "y",
                   "--setactivationskip", "n", new_layer])

    def _add_boot_entry(self, name, rootlv):
        log.info("Adding a boot entry for the new layer")
        eid = uuid()
        edir = self.bls_dir
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
        if not self.dry:
            with open(efile) as dst:
                dst.write("\n".join(entry))

        tmpdir = self.call(["mktemp", "-d"])
        self.call(["mkdir", "-p", tmpdir])
        self.call(["mount", rootlv, tmpdir])
        log.info("Updating fstab of new layer")
        self.call(["sed", "-i", r"/[ \t]\/[ \t]/ s#^[^ \t]\+#%s#" % rootlv,
                   "%s/etc/fstab" % tmpdir])
        self.hooks.trigger("new-layer-added", "/", tmpdir)
        self.call(["umount", rootlv])
        self.call(["rmdir", tmpdir])

    def add_bootable_layer(self):
        log.info("Adding a new layer which can be booted from the bootloader")
        last_layer = self._last_layer().name
        new_layer = self._next_layer().name

        self._add_layer("%s/%s" % (self.vg, last_layer),
                        "%s/%s" % (self.vg, new_layer))
        self._add_boot_entry("%s/%s" % (self.vg, new_layer),
                             "/dev/mapper/%s-%s" % (self.vg, new_layer))

    def add_base(self, infile):
        raise NotImplementedError()

class ImageBuilder(object):
    ksdir = "/usr/share/doc/imgbased/"

    ksnames = ["runtime-layout", "rootfs"]

    def index(self):
        return self.ksnames

    def build(self, ksname):
        if not ksname in self.ksnames:
            raise RuntimeError("Unknown image: %s" % ksname)

        call(["livemedia-creator",
              "--make-diskimage",
              "--ks", "%s.ks" % ksname,
              "--iso", "boot.iso",
              "--vcpus", "4",
              "--image-name", "%s.img" % ksname])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="imgbased")
    subparsers = parser.add_subparsers(title="Sub-commands", dest="command")

    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--dry", action="store_true")

    base_parser = subparsers.add_parser("base",
                                         help="Runtime base handling")
    base_parser.add_argument("--add", action="store_true",
                              help="Add a base layer from a file or stdin")
    base_parser.add_argument("image", nargs="?", type=argparse.FileType('r'),
                             default=sys.stdin,
                             help="File or stdin to use")

    layer_parser = subparsers.add_parser("layer",
                                         help="Runtime layer handling")
    layer_parser.add_argument("--add", action="store_true",
                              default=False, help="Add a new layer")

    image_parser = subparsers.add_parser("image", help="Image creation")
    image_parser.add_argument("--create", dest="image_create",
                              help="Create an image")

    args = parser.parse_args()

    log.debug("Arguments: %s" % args)

    #
    # Get started
    #
    imgbase = ImageLayers()
    imgbase.debug = args.debug
    imgbase.dry = args.dry

    if args.command == "layer":
        if args.add:
            imgbase.add_bootable_layer()

    elif args.command == "base":
        if args.add:
            imgbase.add_base(args.image)

    elif args.command == "image":
        if args.image_create:
            pass

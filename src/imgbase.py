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


def call(*args, **kwargs):
    kwargs["close_fds"] = True
#    log.debug("Calling: %s %s" % (args, kwargs))
    return subprocess.check_output(*args, **kwargs)


def uuid():
    with open("/proc/sys/kernel/random/uuid") as src:
        return src.read().replace("-", "")


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
    baselv = "BaseImage"
    thinpool = "ImagePool"
    layerprefix = "Layer"

    def __init__(self):
        self.hooks = Hooks()

    def call(self, *args, **kwargs):
        log.debug("Calling: %s %s" % (args, kwargs))
        if not self.dry:
            return call(*args, **kwargs)

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
        idx = self.call("lvs | egrep '\s+%s' | wc -l" % self.layerprefix,
                        shell=True)
        previous_layer = "%s%s" % (self.layerprefix, int(idx) + 1) \
            if idx == 0 else self.baselv

        new_layer = "%s%s" % (self.layerprefix, idx)
        self._add_layer("%s/%s" % (self.vg, previous_layer),
                        "%s/%s" % (self.vg, new_layer))
        self._add_boot_entry("%s/%s" % (self.vg, new_layer),
                             "/dev/mapper/%s-%s" % (self.vg, new_layer))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="imgbased")
    subparsers = parser.add_subparsers(title="Sub-commands")

    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--dry", action="store_true")

    layer_parser = subparsers.add_parser("layer", help="Runtime layer handling")
    layer_parser.add_argument("--add", dest="layer_add", action="store_true",
                              help="Add a new layer")

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

    if args.layer_add:
        imgbase.add_bootable_layer()

    elif args.image_create:
        pass


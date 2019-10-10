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
import logging
import inspect
import re

from ..config import paths
from ..utils import BuildMetadata, Fstab, Motd, bcolors
from ..naming import Image
from ..lvm import LVM
from ..bootloader import BootConfiguration
from ..imgbase import LayerNotFoundError


log = logging.getLogger(__package__)


def init(app):
    app.hooks.connect("pre-arg-parse", add_argparse)
    app.hooks.connect("post-arg-parse", post_argparse)


def add_argparse(app, parser, subparsers):
    #
    # base
    #
    base_parser = subparsers.add_parser("base",
                                        help="Runtime base handling")
    base_parser.add_argument("--add",
                             metavar="NAME-VERSION.RELEASE",
                             help="Add a base layer")

    base_parser.add_argument("--remove",
                             metavar="BASE",
                             help="Remove a base layer and it's children")

    base_parser.add_argument("--size",
                             help="(Virtual) Size of the thin volume")

    base_parser.add_argument("--latest", action="store_true",
                             help="Get the most recently added base")

    base_parser.add_argument("--of-layer", metavar="LAYER",
                             help="Get the base of layer LAYER")

    #
    # layer
    #
    layer_parser = subparsers.add_parser("layer",
                                         help="Runtime layer handling")
    layer_parser.add_argument("--add", action="store_true",
                              default=False, help="Add a new layer")
    layer_parser.add_argument("--latest", action="store_true",
                              help="Get the latest layer")
    layer_parser.add_argument("--current", action="store_true",
                              help="Get the current layer used to boot this")
    layer_parser.add_argument("--volume-path", metavar="NVR",
                              help="Get the path to the volume holding "
                              "a layer")
    layer_parser.add_argument("IMAGE", nargs="?",
                              help="Optional to be used with --add")

    subparsers.add_parser("w",
                          help="Check on what layer you are")

    #
    # layout
    layout_parser = subparsers.add_parser("layout",
                                          help="List all bases and layers")
    layout_group = layout_parser.add_mutually_exclusive_group()
    layout_group.add_argument("--free-space", action="store_true",
                              default=False,
                              help="How much space there is in the thinpool")
    layout_group.add_argument("--bases", action="store_true",
                              help="List all bases")
    layout_group.add_argument("--layers", action="store_true",
                              help="List all layers")
    layout_group.add_argument("--init", action="store_true",
                              help="Initialize an imgbased layout")
    layout_group.add_argument("--init-nvr", metavar="NVR",
                              help="Initialize an imgbased layout "
                              "with a given NVR")

    init_group = layout_parser.add_argument_group("Initialization arguments")
    init_group.add_argument("--size",
                            help="Size of the thinpool (in MB)")
    init_group.add_argument("--from", type=str, dest="source", default="/",
                            metavar="VG/LV",
                            help="Make an existing thin LV consumable")

    space_group = layout_parser.add_argument_group("Free space arguments")
    space_group.add_argument("--units", default="m",
                             help="Units to be used for free space")

    #
    # check
    #
    check_parser = subparsers.add_parser("check",
                                         help="Perform some runtime checks")

    #
    # motd
    #
    check_parser = subparsers.add_parser("motd",
                                         help="Get a high-level summary")
    check_parser.add_argument("--update", action="store_true",
                              help="Update /etc/motd")


def post_argparse(app, args):

    if args.command == "base":
        if args.add:
            if not args.size:
                raise RuntimeError("--size is required")
            app.imgbase.add_base(args.size, args.add)
        if args.remove:
            app.imgbase.remove_base(args.remove)
        elif args.latest:
            print(app.imgbase.latest_base())
        elif args.of_layer:
            try:
                print(str(app.imgbase.base_of_layer(args.of_layer)))
            except LayerNotFoundError:
                print("Layer {} was not found, please use imgbase layout "
                      "--layers for a list of available "
                      "layers".format(args.of_layer))

    elif args.command == "layer":
        if args.add:
            if args.IMAGE:
                app.imgbase.add_layer(args.IMAGE)
            else:
                log.warn("Adding new layer onto latest")
                app.imgbase.add_layer_on_latest()
        elif args.current:
            print(app.imgbase.current_layer())
        elif args.latest:
            print(app.imgbase.latest_layer())
        elif args.volume_path:
            layer = Image.from_nvr(args.volume_path)
            print(app.imgbase.lv_from_layer(layer).path)

    elif args.command == "w":
        msg = "You are on %s" % app.imgbase.current_layer()
        log.debug(msg)
        print(msg)

    if args.command == "layout":
        layout = Layout(app)
        if args.init or args.init_nvr:
            layout.initialize(args.source, args.init_nvr)

        elif args.free_space:
            print(app.imgbase.free_space(args.units))
        elif args.bases:
            print("\n".join(str(b) for b in layout.list_bases()))
        elif args.layers:
            print("\n".join(str(l) for l in layout.list_layers()))
        else:
            print(layout.dumps())

    elif args.command == "check":
        run_check(app)

    elif args.command == "motd":
        Motd("/etc/motd").run_motd(Health(app).status().is_ok(), args.update)


class Layout():
    """High-Level functionality of the layuot verb
    """
    class NVRMissingError(Exception):
        pass

    def __init__(self, app):
        self.app = app

    def list_bases(self):
        return self.app.imgbase.naming.bases()

    def list_layers(self):
        return self.app.imgbase.naming.layers()

    def dumps(self):
        return self.app.imgbase.layout()

    def initialize(self, source, init_nvr=None):
        try:
            init_nvr = init_nvr or BuildMetadata().get("nvr")
        except Exception:
            raise Layout.NVRMissingError("There is no NVR set for "
                                         "this build, in this "
                                         "case you need to initialize "
                                         "with --init-nvr")
        self.app.imgbase.init_layout_from(source, init_nvr)
        LVM.stop_monitoring()


def run_check(app):
    status = Health(app).status()
    print(status.details())
    return status.is_ok()


class Health():
    class Check():
        class Result():
            check = None
            ok = None
            traceback = None
            reason = None

        def __init__(self, description=None, run=None, reason=lambda: None):
            self.description = description
            self.checker = run
            self.find_reason = reason

        def run(self):
            result = Health.Check.Result()
            result.check = self
            try:
                result.ok = self.checker()
                assert result.ok in [True, False]
                if not result.ok:
                    result.reason = self.find_reason()
            except Exception as e:
                result.ok = False
                result.traceback = ("Exception in '%s': %r %s" %
                                    (self.checker, e, e))
            return result

    class CheckGroup():
        class Result():
            def __init__(self):
                self.checkgroup = None
                self.results = []

            def is_failed(self):
                return any(r.ok is not True for r in self.results)

            def is_error(self):
                return any(r.traceback for r in self.results)

            def is_ok(self):
                return not self.is_failed() and not self.is_error()

            def __str__(self):
                state = bcolors.ok("OK")
                if self.is_failed():
                    state = bcolors.fail("FAILED")
                elif self.is_error():
                    state = bcolors.warn("ERROR")
                return state

            def oneline(self):
                return "%s ... %s" % (self.checkgroup.description,
                                      self)

            def details(self):
                txts = [self.oneline()]
                if not self.is_ok():
                    txts[0] += " - %s" % self.checkgroup.reason
                for r in self.results:
                    if r.traceback:
                        state = bcolors.warn("ERROR")
                    elif not r.ok:
                        state = bcolors.fail("FAILED")
                        reason = r.reason
                        if reason:
                            state += " - %s" % reason
                    else:
                        state = bcolors.ok("OK")
                    txt = "  %s ... %s" % (r.check.description,
                                           state)
                    if r.traceback:
                        txt += "\n    " + r.traceback
                    txts.append(txt)
                return "\n".join(txts)

        def __init__(self):
            self.description = None
            self.checks = []
            self.reason = None

        def run(self):
            result = Health.CheckGroup.Result()
            result.checkgroup = self
            for check in self.checks:
                result.results.append(check.run())
            return result

    class Status():
        def __init__(self):
            self.results = []

        def __str__(self):
            state = bcolors.ok("OK")
            if self.is_failed():
                state = bcolors.fail("FAILED")
            elif self.is_error():
                state = bcolors.warn("ERROR")
            return state

        def is_failed(self):
            return any(r.is_failed() for r in self.results)

        def is_error(self):
            return any(r.is_error() for r in self.results)

        def is_ok(self):
            return not self.is_failed() and not self.is_error()

        def summary(self):
            txts = [bcolors.bold("Status: %s" % self)]
            for r in self.results:
                txts.append(r.oneline())
            return "\n".join(txts)

        def details(self):
            txts = [bcolors.bold("Status: %s" % self)]
            for r in self.results:
                txts.append(r.details())
            return "\n".join(txts)

    def __init__(self, app):
        self.app = app

    def status(self):
        status = Health.Status()

        for m, group in inspect.getmembers(self):
            if m.startswith("check_"):
                status.results.append(group().run())

        return status

    def check_storage(self):
        group = Health.CheckGroup()
        group.description = "Basic storage"
        group.reason = ("It looks like the LVM layout is not "
                        "correct. The reason could be an "
                        "incorrect installation.")
        group.checks = [
            Health.Check("Initialized VG",
                         lambda: bool(self.app.imgbase._vg)),
            Health.Check("Initialized Thin Pool",
                         lambda: bool(self.app.imgbase._thinpool)),
            Health.Check("Initialized LVs",
                         lambda: bool(self.app.imgbase.list_our_lv_names))
        ]

        return group

    def check_thin(self):
        group = Health.CheckGroup()
        group.description = "Thin storage"
        group.reason = ("It looks like the LVM layout is not "
                        "correct. The reason could be an "
                        "incorrect installation.")
        pool = self.app.imgbase._thinpool()
        datap = None
        try:
            lvs = LVM._lvs(["--noheadings",
                            "-odata_percent,metadata_percent", pool.lvm_name])
            datap, metap = map(float, lvs.replace(",", ".").split())
        except Exception:
            log.debug("Failed to get thin data", exc_info=True)

        if datap is None:
            # Failed to retrieve LVM data
            group.checks = [Health.Check("Checking from thin metadata",
                                         lambda: RuntimeError())]
            return group

        def has_autoextend():
            profile = pool.profile()
            args = ["--metadataprofile", profile] if profile else []
            args += ["--type", "full",
                     "activation/thin_pool_autoextend_threshold"]
            ret = False
            try:
                ret = int(LVM._lvmconfig(args).split("=")[1]) < 100
            except Exception:
                pass
            return ret

        group.checks = [
            Health.Check("Checking available space in thinpool",
                         lambda: all(v < 80 for v in [datap, metap]),
                         lambda: ("Data or Metadata usage is above "
                                  "threshold. Check the output of `lvs`")),
            Health.Check("Checking thinpool auto-extend",
                         has_autoextend,
                         lambda: ("In order to enable thinpool auto-extend,"
                                  "activation/thin_pool_autoextend_threshold "
                                  "needs to be set below 100 in lvm.conf"))
        ]
        return group

    def check_mounts(self):
        group = Health.CheckGroup()
        group.description = "Mount points"
        group.reason = ("This can happen if the installation was "
                        "performed incorrectly")

        def check_discard():
            if not os.path.ismount("/var"):
                return False
            fstab = Fstab("/etc/fstab")

            discards = []

            targets = list(paths.keys()) + ["/"]
            for tgt in targets:
                try:
                    ret = "discard" in fstab.by_target(tgt).options
                    discards.append(ret)
                except KeyError:
                    from six.moves.configparser import ConfigParser
                    c = ConfigParser()
                    c.optionxform = str

                    sub = re.sub(r'^/', '', tgt)
                    sub = re.sub(r'/', '-', tgt)
                    fname = "/etc/systemd/system/{}.mount".format(sub)

                    if os.path.exists(fname):
                        c.read(fname)
                        ret = "discard" in c.get('Mount', 'Options')
                        discards.append(ret)
            is_ok = all(discards)
            return is_ok

        group.checks = [
            Health.Check("Separate /var",
                         lambda: os.path.ismount("/var"),
                         lambda: ("/var got unmounted, or was not setup "
                                  "to use a separate volume")),
            Health.Check("Discard is used",
                         check_discard,
                         lambda: ("'discard' mount option was not "
                                  "added or got removed"))
            ]

        return group

    def check_bootloader(self):
        group = Health.CheckGroup()
        b = BootConfiguration()
        group.description = "Bootloader"
        group.reason = ("It looks like there are no valid bootloader "
                        "entries. Please ensure this is fixed before "
                        "rebooting.")

        def check_node():
            if not b.list():
                return False
            return True

        def check_other():
            if not b.list_other():
                return False
            return True

        group.checks = [
            Health.Check("Layer boot entries",
                         check_node,
                         lambda: ("No bootloader entries which point to "
                                  "imgbased layers")),
            Health.Check("Valid boot entries",
                         lambda: check_node() or check_other(),
                         lambda: ("No valid boot entries for imgbased layers "
                                  "or non-imgbased layers"))
            ]

        return group

# vim: sw=4 et sts=4:

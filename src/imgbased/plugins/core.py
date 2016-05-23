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
import traceback
import inspect
from ..utils import augtool, BuildMetadata
from ..naming import Image
from ..lvm import LVM


log = logging.getLogger(__package__)


def pre_init(app):
    app.hooks.create("register-checks",
                     ("register_func",))


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
    check_parser.add_argument("--fix", action="store_true",
                              help="Try to fix if a check fails")

    #
    # motd
    #
    check_parser = subparsers.add_parser("motd",
                                         help="Get a high-level summary")


def post_argparse(app, args):
    log.debug("Operating on: %s" % app.imgbase)

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
            print(str(app.imgbase.base_of_layer(args.of_layer)))

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
            print(app.imgbase.lv_from_nvr(layer).path)

    elif args.command == "w":
        msg = "You are on %s" % app.imgbase.current_layer()
        log.info(msg)

    if args.command == "layout":
        if args.init or args.init_nvr:
            try:
                init_nvr = args.init_nvr or BuildMetadata().get("nvr")
            except:
                log.error("There is no NVR set for this build, in this "
                          "case you need to initialize with --init-nvr")
            try:
                app.imgbase.init_layout_from(args.source, init_nvr)
            except RuntimeError:
                log.exception("Failed to initialized layout from %r" %
                              args.source)
        elif args.free_space:
            print(app.imgbase.free_space(args.units))
        elif args.bases:
            print("\n".join(str(b) for b in app.imgbase.naming.bases()))
        elif args.layers:
            print("\n".join(str(l) for l in app.imgbase.naming.layers()))
        else:
            print(app.imgbase.layout())

    elif args.command == "check":
        run_check(app, args.fix)

    elif args.command == "motd":
        run_motd(app)


def run_check(app, try_fix):
    checks = []

    def register_func(check):
        checks.append(check)

    app.hooks.emit("register-checks", register_func)

    @register_func
    def health(fix):
        log.info(Health(app).status())
        run = Health(app).check_storage().run()
        log.info("%s" % run)
        log.info("%s" % run.oneline())
        log.info("%s" % run.details())

    log.debug("Running checks: %s" % checks)

    any_fail = False
    for check in checks:
        if not check(try_fix):
            any_fail = True

    if any_fail:
        log.warn("There were warnings")
    else:
        log.info("The check completed without warnings")

    return any_fail


class Health():
    class Check():
        def __init__(self, description=None, run=None, reason=lambda: None):
            self.description = description
            self.run = run
            self.reason = reason

    class CheckResult():
        check = None
        ok = None
        traceback = None

    class CheckGroup():
        def __init__(self):
            self.description = None
            self.reason = None
            self.checks = []

        def run(self):
            status = Health.Status()
            status.group = self
            for check in self.checks:
                result = Health.CheckResult()
                result.check = check
                try:
                    result.ok = True if check.run() else False
                    if not result.ok:
                        result.reason = check.reason()
                except:
                    result.ok = False
                    result.traceback = traceback.format_exc()
                status.results.append(result)
            return status

    class Status():
        def __init__(self):
            self.group = None
            self.results = []

        def __repr__(self):
            return "<%s - %s />" % (self.group.description, self)

        def __str__(self):
            state = "OK"
            if any(r.traceback for r in self.results):
                state = "ERROR"
            elif any(r.ok == False for r in self.results):
                state = "FAILED"
            return state

        def oneline(self):
            return "%s: %s" % (self.group.description, self)

        def details(self):
            txts = []
            for r in self.results:
                if r.traceback:
                    state = "ERROR"
                else:
                    state = "OK" if r.ok else "FAILED"
                txt = "%s ... %s" % (r.check.description,
                                     state)
                if r.traceback:
                    txt += "\n" + r.traceback
                txts.append(txt)
            return "\n".join(txts)

    def __init__(self, app):
        self.app = app

    def _run(self):
        for m, group in inspect.getmembers(self):
            if m.startswith("check_"):
                yield group().run()

    def status(self):
        return list(self._run())

    def check_storage(self):
        group = Health.CheckGroup()
        group.description = "Basic storage"
        group.failure_reason = ("It looks like the LVM layout is not "
                                "correct. The reason could be an "
                                "incorrect installation.")
        group.checks = [
            Health.Check("Initialized VG",
                         self.app.imgbase._vg),
            Health.Check("Initialized Thin Pool",
                         self.app.imgbase._thinpool),
            Health.Check("Initialized LVs",
                         self.app.imgbase.list_our_lv_names)
        ]

        return group

    def check_thin(self):
        group = Health.CheckGroup()
        group.description = "Thin storage"
        group.failure_reason = ("It looks like the LVM layout is not "
                                "correct. The reason could be an "
                                "incorrect installation.")

        datap = None
        try:
            lvs = LVM._lvs(["--noheadings",
                            "-odata_percent,metadata_percent",
                            app.imgbase._thinpool().lvm_name])
            datap, metap = map(float, lvs.replace(",", ".").split())
        except:
            log.debug("Failed to get thin data", exc_info=True)

        if datap == None:
            group.checks = [Health.Check("Checking from thin metadata",
                                         lambda: False)
                           ]
        else:
            def has_autoextend():
                ap = ("/files/etc/lvm/lvm.conf/activation/dict/"
                      "thin_pool_autoextend_threshold/int")

                if augtool("get", ap).endswith("= 0"):
                    log.warn("Thinpool autoextend is disabled, must be enabled")
                    fail = True
                    if try_fix:
                        log.info("Thinpool autoextend is disabled, enabling")
                        augtool("set", "-s", ap, "80")
                else:
                    log.debug("Thinpool autoextend is set")
            group.checks = [
                Health.Check("Checking available space in thinpool",
                             lambda: any(v > 80 for v in [datap, metap]),
                             lambda: ("Data or Metadata usage is above "
                                      "threshold. Check teh output of `lvs`")),
                Health.Check("Checking thinpool auto-extend",
                             has_autoextend,
                             "thin_pool_autoextend_threshold needs to be "
                             "set in lvm.conf")
            ]


        return group


def run_motd(app):
    fail = run_check(app, False)
    if fail:
        log.error("Status: DEGRADED")
        log.error("Please check the status manually using"
                  " `imgbase check`")
    else:
        log.info("Status: OK")


# vim: sw=4 et sts=4:

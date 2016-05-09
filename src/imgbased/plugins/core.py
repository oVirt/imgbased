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
from ..utils import augtool, BuildMetadata


log = logging.getLogger(__package__)


def pre_init(app):
    app.hooks.create("register-checks",
                     ("register_func",))


def init(app):
    app.hooks.connect("pre-arg-parse", add_argparse)
    app.hooks.connect("post-arg-parse", check_argparse)


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


def check_argparse(app, args):
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


def run_check(app, try_fix):
    checks = []

    def register_func(check):
        checks.append(check)

    app.hooks.emit("register-checks", register_func)

    from ..lvm import LVM
    lvs = LVM._lvs(["--noheadings", "-odata_percent,metadata_percent",
                    app.imgbase._thinpool().lvm_name])
    datap, metap = map(float, lvs.replace(",", ".").split())

    @register_func
    def thin_check(try_fix):
        log.info("Checking available space in thinpool")
        fail = any(v > 80 for v in [datap, metap])
        if fail:
            log.warning("Data or Metadata usage is above threshold:")
            print(LVM._lvs([app.imgbase._thinpool().lvm_name]))
        return fail

    @register_func
    def thin_extend_check(try_fix):
        fail = False
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
        return fail

    log.debug("Running checks: %s" % checks)

    any_fail = False
    for check in checks:
        if not check(try_fix):
            any_fail = True

    if any_fail:
        log.warn("There were warnings")
    else:
        log.info("The check completed without warnings")


# vim: sw=4 et sts=4:

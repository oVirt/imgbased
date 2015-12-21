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
import sys
import argparse
import logging


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
                             nargs=3,
                             metavar=("NAME","VERSION","RELEASE"),
                             help="Add a base layer")
    base_parser.add_argument("--add-with-tree",
                             metavar="PATH_TO_TREE",
                             help="Add a base layer from an fs tree")

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
    layout_group.add_argument("--init-from", type=str, default="",
                              metavar="VG/LV",
                              help="Make an existing thin LV consumable")
    layout_group.add_argument("--bases", action="store_true",
                              help="List all bases")
    layout_group.add_argument("--layers", action="store_true",
                              help="List all layers")

    space_group = layout_parser.add_argument_group("Free space arguments")
    space_group.add_argument("--units", default="m",
                             help="Units to be used for free space")
    init_group = layout_parser.add_argument_group("Initialization arguments")
    init_group.add_argument("--size",
                            help="Size of the thinpool (in MB)")
    init_group.add_argument("pv", nargs="*", metavar="PV",
                            type=argparse.FileType(),
                            help="LVM PVs to use")

    #
    # check
    #
    subparsers.add_parser("check",
                          help="Perform some runtime checks")


def check_argparse(app, args):
    log.debug("Operating on: %s" % app.imgbase)

    if args.command == "base":
        if args.add:
            if not args.size:
                raise RuntimeError("--size is required")
            app.imgbase.add_base(args.size, *args.add)
        elif args.add_with_tree:
            if not args.size:
                raise RuntimeError("--size")
            app.imgbase.add_base_with_tree(args.add_with_tree, args.size)
        if args.remove:
            print(args)
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
        if args.init_from:
            app.imgbase.init_layout_from(args.init_from)
        elif args.free_space:
            print(app.imgbase.free_space(args.units))
        elif args.bases:
            print("\n".join(str(b) for b in app.imgbase.naming.bases()))
        elif args.layers:
            print("\n".join(str(l) for l in app.imgbase.naming.layers()))
        else:
            print(app.imgbase.layout())

    elif args.command == "check":
        run_check(app)


def run_check(app):
    checks = []

    def register_func(check):
        checks.append(check)

    app.hooks.emit("register-checks", register_func)

    from ..lvm import LVM
    lvs = LVM._lvs(["--noheadings", "-odata_percent,metadata_percent",
                    app.imgbase._thinpool().lvm_name])
    datap, metap = map(float, lvs.replace(",", ".").split())

    def thin_check():
        log.info("Checking available space in thinpool")
        fail = any(v > 80 for v in [datap, metap])
        if fail:
            log.warning("Data or Metadata usage is above threshold:")
            print(LVM._lvs([app.imgbase._thinpool().lvm_name]))
        return fail

    checks += [thin_check]

    log.debug("Running checks: %s" % checks)

    any_fail = False
    for check in checks:
        if not check():
            any_fail = True

    if any_fail:
        log.warn("There were warnings")
    else:
        log.info("The check completed without warnings")


# vim: sw=4 et sts=4:

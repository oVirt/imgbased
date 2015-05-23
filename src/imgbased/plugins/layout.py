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

from ..utils import log
import argparse


def init(app):
    app.hooks.connect("pre-arg-parse", add_argparse)
    app.hooks.connect("post-arg-parse", check_argparse)


def add_argparse(app, parser, subparsers):
    layout_parser = subparsers.add_parser("layout",
                                          help="List all bases and layers")
    layout_group = layout_parser.add_mutually_exclusive_group()
    layout_group.add_argument("--free-space", action="store_true",
                              default=False,
                              help="How much space there is in the thinpool")
    layout_group.add_argument("--init", action="store_true", default=False,
                              help="Create the initial Volume Group")
    layout_group.add_argument("--init-from", type=str, default="",
                              metavar="VG/LV",
                              help="Make an existing thin LV consumable")

    space_group = layout_parser.add_argument_group("Free space arguments")
    space_group.add_argument("--units", default="m",
                             help="Units to be used for free space")
    init_group = layout_parser.add_argument_group("Initialization arguments")
    init_group.add_argument("--size",
                            help="Size of the thinpool (in MB)")
    init_group.add_argument("pv", nargs="*", metavar="PV", type=argparse.FileType(),
                            help="LVM PVs to use")
    init_group.add_argument("--without-vg", action="store_true", default=False,
                            help="Do not create a Volume Group")


def check_argparse(app, args):
    log().debug("Operating on: %s" % app.imgbase)
    if args.command == "layout":
        if args.init:
            if not args.size:
                raise RuntimeError("--size required")
            app.imgbase.init_layout(args.pv, args.size)
        elif args.init_from:
            app.imgbase.init_layout_from(args.init_from)
        elif args.free_space:
            print(app.imgbase.free_space(args.units))
        else:
            print(app.imgbase.layout())

# vim: sw=4 et sts=4

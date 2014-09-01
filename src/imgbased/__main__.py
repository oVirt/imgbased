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
import argparse
import sys
from . import config
from .imgbase import ImageLayers, ExternalBinary


def log():
    return logging.getLogger("imgbase")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="imgbase")
    parser.add_argument("--version", action="version",
                        version=config.version())

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
    layout_group = layout_parser.add_mutually_exclusive_group()
    layout_group.add_argument("--free-space", action="store_true",
                              default=False,
                              help="How much space there is in the thinpool")
    layout_group.add_argument("--init", action="store_true", default=False,
                              help="Create the initial Volume Group")
    space_group = layout_parser.add_argument_group("Free space arguments")
    space_group.add_argument("--units", default="m",
                             help="Units to be used for free space")
    init_group = layout_parser.add_argument_group("Initialization arguments")
    init_group.add_argument("--size",
                            help="Size of the thinpool (in MB)")
    init_group.add_argument("pv", nargs="*", metavar="PV", type=file,
                            help="LVM PVs to use")
    init_group.add_argument("--without-vg", action="store_true", default=False,
                            help="Do not create a Volume Group")

    base_parser = subparsers.add_parser("base",
                                        help="Runtime base handling")
    base_parser.add_argument("--add", action="store_true",
                             help="Add a base layer from a file or stdin")
    base_parser.add_argument("--size",
                             help="(Virtual) Size of the thin volume")
    base_parser.add_argument("--latest", action="store_true",
                             help="Get the most recently added base")
    base_parser.add_argument("--of-layer", metavar="LAYER",
                             help="Get the base of layer LAYER")
    base_parser.add_argument("image", nargs="?", type=argparse.FileType('r'),
                             default=sys.stdin,
                             help="File or stdin to use")

    layer_parser = subparsers.add_parser("layer",
                                         help="Runtime layer handling")
    layer_parser.add_argument("--add", action="store_true",
                              default=False, help="Add a new layer")
    layer_parser.add_argument("--latest", action="store_true",
                              help="Get the latest layer")

    layer_parser = subparsers.add_parser("diff",
                                         help="Compare layers and bases")
    layer_parser.add_argument("image", nargs=2,
                              help="Base/Layer to compare")

    layer_parser = subparsers.add_parser("nspawn",
                                         help="Start a container in a layer")
    layer_parser.add_argument("image",
                              help="Base/Layer to use")

    args = parser.parse_args()

    lvl = logging.DEBUG if args.debug else logging.INFO
    print logging.getLogger().handlers
    logging.basicConfig(level=lvl)
    print logging.getLogger().handlers

    log().debug("Arguments: %s" % args)

    #
    # Get started
    #
    imgbase = ImageLayers()
    imgbase.vg = args.vg
    imgbase.thinpool = args.thinpool
    imgbase.layerformat = args.layerformat
    imgbase.debug = args.debug
    imgbase.dry = args.dry

    ExternalBinary.dry = args.dry

    if args.command == "layout":
        if args.init:
            if not args.size or not args.pv:
                raise RuntimeError("--size and PVs required")
            imgbase.init_layout(args.pv, args.size, args.without_vg)
        elif args.free_space:
            print(imgbase.free_space(args.units))
        else:
            print(imgbase.layout())

    elif args.command == "layer":
        if args.add:
            imgbase.add_bootable_layer()
        elif args.latest:
            print (imgbase.latest_layer())

    elif args.command == "base":
        if args.add:
            if not args.size or not args.image:
                raise RuntimeError("--size and image required")
            imgbase.add_base(args.image, args.size)
        elif args.latest:
            print (imgbase.latest_base())
        elif args.of_layer:
            print (str(imgbase.base_of_layer(args.of_layer)))

    elif args.command == "diff":
        if len(args.image) == 2:
            sys.stdout.writelines(imgbase.diff(*args.image))

    elif args.command == "nspawn":
        if args.image:
            imgbase.nspawn(args.image)

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
from . import config
from .imgbase import ImageLayers, ExternalBinary
from .hooks import Hooks
from . import plugins
from .utils import log


class Application(object):
    imgbase = None
    hooks = None

    def __init__(self):
        self.imgbase = ImageLayers()

        self.hooks = Hooks(context=self)
        self.hooks.create("pre-arg-parse", ("parser", "subparser"))
        self.hooks.create("post-arg-parse", ("parser_args",))

        plugins.init(self)


if __name__ == '__main__':
    app = Application()

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
    layout_group.add_argument("--init-from", type=str, default="",
                              metavar="VG/LV",
                              help="Make an existing thin LV consumable")

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

    layer_parser = subparsers.add_parser("layer",
                                         help="Runtime layer handling")
    layer_parser.add_argument("--add", action="store_true",
                              default=False, help="Add a new layer")
    layer_parser.add_argument("--latest", action="store_true",
                              help="Get the latest layer")
    layer_parser.add_argument("--current", action="store_true",
                              help="Get the current layer used to boot this")

    app.hooks.emit("pre-arg-parse", parser, subparsers)

    args = parser.parse_args()

    lvl = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=lvl)

    log().debug("Arguments: %s" % args)

    #
    # Get started
    #
    app.imgbase.vg = args.vg
    app.imgbase.thinpool = args.thinpool
    app.imgbase.layerformat = args.layerformat
    app.imgbase.debug = args.debug
    app.imgbase.dry = args.dry

    ExternalBinary.dry = args.dry

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

    elif args.command == "layer":
        if args.add:
            app.imgbase.add_bootable_layer()
        elif args.current:
            print (app.imgbase.current_layer())
        elif args.latest:
            print (app.imgbase.latest_layer())

    #
    # Now let the plugins check if they need to run something
    #
    app.hooks.emit("post-arg-parse", args)

# vim: et sts=4 sw=4:

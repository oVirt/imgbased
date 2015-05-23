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
from ..utils import log


def init(app):
    app.hooks.connect("pre-arg-parse", add_argparse)
    app.hooks.connect("post-arg-parse", check_argparse)


def add_argparse(app, parser, subparsers):
    base_parser = subparsers.add_parser("base",
                                        help="Runtime base handling")
    base_parser.add_argument("--add", action="store_true",
                             help="Add a base layer")
    base_parser.add_argument("--add-with-image", action="store_true",
                             help="Add a base layer from an fs image")
    base_parser.add_argument("--add-with-tree", action="store_true",
                             help="Add a base layer from an fs tree")
    base_parser.add_argument("--size",
                             help="(Virtual) Size of the thin volume")
    base_parser.add_argument("--latest", action="store_true",
                             help="Get the most recently added base")
    base_parser.add_argument("--of-layer", metavar="LAYER",
                             help="Get the base of layer LAYER")
    base_parser.add_argument("image", nargs="?", type=argparse.FileType('r'),
                             default=sys.stdin,
                             help="File or stdin to use")


def check_argparse(app, args):
    log().debug("Operating on: %s" % app.imgbase)
    if args.command == "base":
        if args.add:
            if not args.size:
                raise RuntimeError("--size is required")
            app.imgbase.add_base(args.size)
        elif args.add_with_image:
            if not args.size or not args.image:
                raise RuntimeError("--size and image required")
            app.imgbase.add_base_from_image(args.image)
        elif args.add_with_tree:
            if not args.size or not args.image:
                raise RuntimeError("--size and image required")
            app.imgbase.add_base_with_tree(args.image, args.size)
        elif args.latest:
            print(app.imgbase.latest_base())
        elif args.of_layer:
            print(str(app.imgbase.base_of_layer(args.of_layer)))

# vim: sw=4 et sts=4

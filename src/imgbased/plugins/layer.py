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


log = logging.getLogger(__package__)


def init(app):
    app.hooks.connect("pre-arg-parse", add_argparse)
    app.hooks.connect("post-arg-parse", check_argparse)


def add_argparse(app, parser, subparsers):
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


def check_argparse(app, args):
    log.debug("Operating on: %s" % app.imgbase)
    if args.command == "layer":
        if args.IMAGE == "w":
           msg = "You are on %s" % app.imgbase.current_layer()
           log.info(msg)
        if args.add:
            # FIXME we could optionally allopw latest/current/specific
            if args.latest:
                app.imgbase.add_layer_on_latest()
            elif args.IMAGE:
                app.imgbase.add_layer(args.IMAGE)
            else:
                # current is default
                app.imgbase.add_layer_on_latest()
        elif args.current:
            print(app.imgbase.current_layer())
        elif args.latest:
            print(app.imgbase.latest_layer())

# vim: sw=4 et sts=4

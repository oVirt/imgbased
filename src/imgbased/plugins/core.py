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
    base_parser = subparsers.add_parser("base",
                                        help="Runtime base handling")
    base_parser.add_argument("--add", action="store_true",
                             help="Add a base layer")
    base_parser.add_argument("--add-with-tree",
                             help="Add a base layer from an fs tree")
    base_parser.add_argument("--add-with-image",
                             help="Add a base layer from an fs image",
                             nargs="?", type=argparse.FileType('r'),
                             default=None)
    base_parser.add_argument("--size",
                             help="(Virtual) Size of the thin volume")
    base_parser.add_argument("--latest", action="store_true",
                             help="Get the most recently added base")
    base_parser.add_argument("--of-layer", metavar="LAYER",
                             help="Get the base of layer LAYER")

    subparsers.add_parser("check",
                          help="Perform some runtime checks")


def check_argparse(app, args):
    log.debug("Operating on: %s" % app.imgbase)
    if args.command == "base":
        if args.add:
            if not args.size:
                raise RuntimeError("--size is required")
            app.imgbase.add_base(args.size)
        elif args.add_with_image:
            if not args.size:
                raise RuntimeError("--size is required")
            app.imgbase.add_base_from_image(args.add_with_image or sys.stdin)
        elif args.add_with_tree:
            if not args.size:
                raise RuntimeError("--size")
            app.imgbase.add_base_with_tree(args.add_with_tree, args.size)
        elif args.latest:
            print(app.imgbase.latest_base())
        elif args.of_layer:
            print(str(app.imgbase.base_of_layer(args.of_layer)))
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

    any_fail = False
    for check in checks:
        fail = check()
        any_fail = True if fail else False

    if any_fail:
        log.warn("There were warnings")
    else:
        log.info("The check completed without warnings")


# vim: sw=4 et sts=4:

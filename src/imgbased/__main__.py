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


log = logging.getLogger(__package__)


class Application(object):
    imgbase = None
    hooks = None

    def __init__(self):
        self.imgbase = ImageLayers()

        self.hooks = Hooks(context=self)
        self.hooks.create("pre-arg-parse", ("parser", "subparser"))
        self.hooks.create("post-arg-parse", ("parser_args",))

        plugins.init(self)


def setup_logging():
    log.setLevel(logging.INFO)

    info = (logging.INFO, "%(message)s")
    debug = (logging.DEBUG, "%(asctime)s - %(levelname)s - %(message)s")

    def addHandler(lvl, fmt):
        h = logging.StreamHandler()
        h.setLevel(lvl)
        h.setFormatter(logging.Formatter(fmt))
        log.addHandler(h)

    for lvl, fmt in [info, debug]:
        addHandler(lvl, fmt)


if __name__ == '__main__':
    setup_logging()

    app = Application()

    parser = argparse.ArgumentParser(description="imgbase")
    parser.add_argument("--version", action="version",
                        version=config.version())

    subparsers = parser.add_subparsers(title="Sub-commands", dest="command")

    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--dry", action="store_true")
    parser.add_argument("--layerformat", help="Format to discover layers",
                        default=ImageLayers.layerformat)

    app.hooks.emit("pre-arg-parse", parser, subparsers)

    args = parser.parse_args()

    if args.debug:
        log.setLevel(logging.DEBUG)

    log.debug("Arguments: %s" % args)

    #
    # Get started
    #
    app.imgbase.layerformat = args.layerformat
    app.imgbase.debug = args.debug
    app.imgbase.dry = args.dry

    ExternalBinary.dry = args.dry

    #
    # Now let the plugins check if they need to run something
    #
    app.hooks.emit("post-arg-parse", args)

# vim: et sts=4 sw=4:

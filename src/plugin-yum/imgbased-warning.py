# -*- coding: utf-8 -*-
#
# Warning message to imgbased users, via a yum plugin
#
# Copyright © 2016 Red Hat, Inc.
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

from yum.plugins import TYPE_INTERACTIVE

requires_api_version = '2.3'
plugin_type = (TYPE_INTERACTIVE)


def init_hook(conduit):
    conduit.info(2, '\x1b[31mWarning: yum operations are not persisted '
                    'across upgrades!\x1b[0m\r')

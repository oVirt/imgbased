# -*- coding: utf-8 -*-
#
# Warning message to imgbased users, via a dnf plugin
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

import dnf


class ImgbasedWarning(dnf.Plugin):

    name = 'imagebased-warning'

    def config(self):
        print('\x1b[31mWarning: dnf operations are not persisted '
              'across upgrades!\x1b[0m\r')

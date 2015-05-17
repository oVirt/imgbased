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
from .utils import ExternalBinary


class LVM(object):
    _lvs = ExternalBinary().lvs

    class LV(object):
        vg_name = None
        lv_name = None

        @property
        def lvm_name(self):
            """With lvm_name we referre to the combination of VG+LV: VG/LV
            """
            return "%s/%s" % (self.vg_name, self.lv_name)

        @property
        def path(self):
            return LVM._lvs(["--noheadings", "-olv_path", self.lvm_name])

        def __init__(self, vg_name, lv_name):
            self.vg_name = vg_name
            self.lv_name = lv_name

        @staticmethod
        def from_lvm_name(lvm_name):
            """Easy way to get an opbject for the lvm name

            >>> lv = LVM.LV.from_lvm_name("HostVG/Foo")
            >>> lv.vg_name
            'HostVG'
            >>> lv.lv_name
            'Foo'
            """
            return LVM.LV(*lvm_name.split("/"))

        @staticmethod
        def from_path(path):
            """Get an object for the path
            """
            data = LVM._lvs(["--noheadings", "-olv_name,vg_name", path])
            assert data, "Failed to find LV for path: %s" % path
            return LVM.LV(*data.split(" "))

# vim: sw=4 et sts=4

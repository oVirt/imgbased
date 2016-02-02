#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# imgbase
#
# Copyright (C) 2015  Red Hat, Inc.
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

from logging import debug

import imgbased


class FakeLVM(imgbased.lvm.LVM):
    _vgs = []

    @staticmethod
    def list_lv_names(tags=[]):
        lvs = [lv for lv in FakeLVM.lvs()]
        debug("LVS %s" % lvs)
        if tags:
            lvs = [lv for lv in lvs if any(tag in lv._tags for tag in tags)]
            debug("Tagged LVS %s" % lvs)
        return [lv.lv_name for lv in lvs]

    @staticmethod
    def lvs():
        lvs = []
        for vg in FakeLVM._vgs:
            lvs.extend(lv for lv in vg._lvs)
        return lvs

    class VG(imgbased.lvm.LVM.VG):
        vg_name = None
        _tags = None
        _pvs = None
        _lvs = None

        def __init__(self, vg_name=None):
            self.vg_name = vg_name
            self._tags = set()
            self._pvs = set()
            self._lvs = set()

        @staticmethod
        def from_vg_name(vg_name):
            debug("Looking for %r in Available VGs: %s" %
                  (vg_name, FakeLVM._vgs))
            return [vg for vg in FakeLVM._vgs
                    if vg.vg_name == vg_name].pop()

        @staticmethod
        def find_by_tag(tag):
            debug("Finding VG by tag %s" % tag)
            vg = [g for g in FakeLVM._vgs
                  if tag in g.tags()]
            debug("Found: %s" % vg)
            return vg

        @staticmethod
        def from_tag(tag):
            vgs = FakeLVM.VG.find_by_tag(tag)
            assert len(vgs) == 1
            return vgs[0]

        @staticmethod
        def create(vg_name, pv_paths):
            vg = FakeLVM.VG(vg_name)
            vg._pvs = pv_paths
            FakeLVM._vgs.append(vg)
            debug("Creating %s" % vg)
            return vg

        def addtag(self, tag):
            debug("Adding tag %s to %s" % (tag, self))
            self._tags.add(tag)
            debug("Now has: %s" % str(self._tags))

        def tags(self):
            return self._tags

    class LV(imgbased.lvm.LVM.LV):
        vg_name = None
        lv_name = None

        _tags = None
        _thin = False
        _pool = False
        _size = None
        _origin = None
        _active = True
        _activationskip = False
        _permission = "rw"
        _pool_lv = None

        def __init__(self):
            self._tags = set()

        @property
        def path(self):
            return "/dev/%s/%s" % (self.vg_name, self.lv_name)

        @staticmethod
        def find_by_tag(tag):
            return [v for v in FakeLVM.lvs()
                    if tag in v.tags()]

        @staticmethod
        def from_lv_name(vg_name, lv_name):
            vg = FakeLVM.VG.from_vg_name(vg_name)
            try:
                return [lv for lv in vg._lvs
                        if lv.lv_name == lv_name].pop()
            except IndexError:
                raise IndexError("Could not find LV: %s/%s" %
                                 (vg_name, lv_name))

        @staticmethod
        def from_path(path):
            raise NotImplementedError()

        def create_snapshot(self, new_name):
            lv = FakeLVM.LV()
            lv.vg_name = self.vg_name
            lv.lv_name = new_name
            lv._thin = self._thin
            lv._size = self._size
            lv._origin = self
            lv._active = False if self._thin else True
            lv._activationskip = True if self._thin else False
            lv._permission = self._permission
            debug("Adding LV %s to VG %s" % (lv, lv.vg_name))
            FakeLVM.VG.from_vg_name(lv.vg_name)._lvs.add(lv)
            return lv

        def remove(self, force=False):
            FakeLVM.VG.from_vg_name(self.vg_name)._lvs.remove(self)

        def activate(self, val, ignoreactivationskip=False):
            assert val in [True, False]
            if not self._activationskip:
                self._active = val
            elif self._activationskip and ignoreactivationskip:
                self._active = val

        def setactivationskip(self, val):
            assert val in [True, False]
            self._activationskip = val

        def permission(self, val):
            assert val in ["r", "rw"]
            self._permission = val

        def thinpool(self):
            debug("Thinpool of %s: %s" % (self, self._pool_lv))
            return self._pool_lv

        def addtag(self, tag):
            self._tags.add(tag)

        def tags(self):
            return self._tags

        def origin(self):
            return self._origin

        def options(self, options):
            raise NotImplementedError()

    class Thinpool(LV):
        _virtualsize = None

        def __init__(self):
            FakeLVM.LV.__init__(self)
            self._thin = True
            self._pool = True

        def create_thinvol(self, vol_name, volsize):
            lv = FakeLVM.LV()
            lv.vg_name = self.vg_name
            lv.lv_name = vol_name
            lv.size = volsize
            lv._virtualsize = volsize
            lv._thin = True
            lv._pool_lv = self
            FakeLVM.VG.from_vg_name(lv.vg_name)._lvs.add(lv)
            debug("Created thin LV: %s" % lv)
            return lv

# vim: et ts=4 sw=4 sts=4

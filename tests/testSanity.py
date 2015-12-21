#!/usr/bin/env python
# vim: et ts=4 sw=4 sts=4

import unittest
import logging
from mock import patch

import imgbased.__main__
import imgbased.lvm


log = logging.info


class FakeLVM(imgbased.lvm.LVM):
    _vgs = []

    @staticmethod
    def lvs():
        lvs = []
        for vg in FakeLVM._vgs:
            lvs.extend(lv.lv_name for lv in vg._lvs)
        return lvs

    class VG(imgbased.lvm.LVM.VG):
        vg_name = None
        _tags = None
        _pvs = None
        _lvs = None

        def __init__(self):
            self._tags = set()
            self._pvs = set()
            self._lvs = set()

        @staticmethod
        def find_by_tag(tag):
            return [g for g in FakeLVM._vgs
                    if tag in g.tags()]

        @staticmethod
        def from_tag(tag):
            vgs = FakeLVM.VG.find_by_tag(tag)
            assert len(vgs) == 1
            return vgs[0]

        @staticmethod
        def create(vg_name, pv_paths):
            vg = FakeLVM.VG()
            vg.vg_name = vg_name
            vg._pvs = pv_paths
            return vg

        def create_thinpool(self, name, size):
            thinlv = FakeLVM.LV()
            thinlv.vg_name = self.vg_name
            thinlv.lv_name = name
            thinlv._thin = True
            thinlv._pool = True
            thinlv._size = size
            self._lvs.append(thinlv)
            return thinlv

        def addtag(self, tag):
            self._tags.add(tag)

        def tags(self):
            return self._tags

    class LV(imgbased.lvm.LVM.LV):
        vg_name = None
        lv_name = None

        _thin = False
        _pool = False
        _size = None
        _origin = None
        _active = True
        _activationskip = False
        _permission = "rw"

        @property
        def path(self):
            raise NotImplementedError()

        @staticmethod
        def find_by_tag(tag):
            return [v for v in FakeLVM.lvs()
                    if tag in v.tags()]

        @staticmethod
        def from_path(path):
            raise NotImplementedError()

        def create_snapshot(self, new_name):
            lv = FakeLVM.LV(self.vg_name, new_name)
            lv._thin = self._thin
            lv._size = self._size
            lv._origin = self
            lv._active = False if self._thin else True
            lv._activationskip = True if self._thin else False
            lv._permission = self._permission
            self._vgs.append(lv)

        def remove(self, force=False):
            raise NotImplementedError()

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
            raise NotImplementedError()

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

        def create_thinvol(self, vol_name, volsize):
            lv = FakeLVM.LV(self.vg_name, vol_name)
            lv.size = volsize
            lv._virtualsize = volsize
            lv._thin = True
            return lv


@patch("imgbased.lvm.LVM", FakeLVM)
@patch("imgbased.imgbase.LVM", FakeLVM)
def imgbase(*args):
    try:
        imgbased.__main__.CliApplication(args)
    except SystemExit as e:
        if e.code != 0:
            raise


def autopart():
    vg = FakeLVM.VG()
    vg.vg_name = "hostvg"
    vg._pvs = ["/dev/sda", "/dev/sdb"]

    lv0 = FakeLVM.LV(vg.vg_name, "Image-1.0")
    lv1 = FakeLVM.LV(vg.vg_name, "Image-1.1")
    vg._lvs = [lv0, lv1]

    FakeLVM._vgs = [vg]
    print(FakeLVM.lvs())


class TestImgbased(unittest.TestCase):

    def setUp(self):
        autopart()

    def test_layout(self):
        log(imgbase("--version"))
        imgbase("layout")

    def test_base(self):
        with self.assertRaises(RuntimeError):
            imgbase("base", "--add", "Bar")

        imgbase("base", "--add", "Bar", "--size", "4096")

        print(FakeLVM.lvs())


if __name__ == "__main__":
    unittest.main()

# vim: sw=4 et sts=4

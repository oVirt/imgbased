#!/usr/bin/env python
# vim: et ts=4 sw=4 sts=4

import unittest
import logging
from logging import debug
from mock import patch
from StringIO import StringIO
import sys
from collections import namedtuple

from imgbased import CliApplication
import imgbased.lvm

def logcall(func):
    def wraped(*args, **kwargs):
        try:
            v = func(*args, **kwargs)
        except Exception as e:
            print("%s(%s, %s) EE %s" % (func, args, kwargs, e))
            raise
        print("%s(%s, %s) -> %s" % (func, args, kwargs, v))
        return v
    return wraped

class FakeLVM(imgbased.lvm.LVM):
    _vgs = []

    @staticmethod
    def list_lv_names():
        return [lv.lv_name for lv in FakeLVM.lvs()]

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

        def __init__(self):
            self._tags = set()
            self._pvs = set()
            self._lvs = set()

        @staticmethod
        def from_vg_name(vg_name):
            debug("Available VGs: %s" % FakeLVM._vgs)
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
            vg = FakeLVM.VG()
            vg.vg_name = vg_name
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
        @logcall
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


class ImgbaseTestCase(unittest.TestCase):
    def autopart(self):
        vg = FakeLVM.VG()
        vg.vg_name = "hostvg"
        vg._pvs = ["/dev/sda", "/dev/sdb"]
        FakeLVM._vgs = [vg]

        pool = FakeLVM.Thinpool()
        pool.vg_name = vg.vg_name
        pool.lv_name = "pool0"
        pool.size = 10*1024
        vg._lvs.add(pool)

        lvroot = pool.create_thinvol("root", 10)

        print(FakeLVM.lvs())

    def setUp(self):
        self.autopart()

class ImgbasedCliTestCase(ImgbaseTestCase):
    def cli(self, *args):
        debug("$ imgbased %s" % str(args))
        with patch("imgbased.imgbase.ExternalBinary"), \
                patch("imgbased.lvm.LVM", FakeLVM), \
                patch("imgbased.imgbase.LVM", FakeLVM), \
                patch("imgbased.imgbase.Hooks"), \
                patch("imgbased.imgbase.ImageLayers.current_layer", lambda s: None):
            try:
                olderr = sys.stderr
                oldout = sys.stdout
                sys.stdout = StringIO()
                sys.stderr = StringIO()

                CliApplication(args)

                stdout, stderr = sys.stdout, sys.stderr

            except SystemExit as e:
                if e.code != 0:
                    logging.error(sys.stderr.getvalue())
                    raise

            finally:
                sys.stdout = oldout
                sys.stderr = olderr

        Retval = namedtuple("Returnvalues", ["stdout", "stderr"])
        return Retval(stdout.getvalue(), stderr.getvalue())

    def setUp(self):
        ImgbaseTestCase.setUp(self)
        self.cli("--debug", "layout", "--init-from", "hostvg/root")


class TestLayoutVerb(ImgbasedCliTestCase):
    def test_layout_init_from(self):
        assert "Image-0.0" in FakeLVM.list_lv_names()
        assert "Image-0.1" in FakeLVM.list_lv_names()

    def test_layout_bases(self):
        r = self.cli("--debug", "layout", "--bases")
        debug("Bases: %s" % r.stdout)
        assert r.stdout.strip() == "Image-0.0"

    def test_layout_bases(self):
        r = self.cli("--debug", "layout", "--layers")
        debug("Layers: %s" % r.stdout)
        assert r.stdout.strip() == "Image-0.1"


class TestBaseVerb(ImgbasedCliTestCase):
    def test_base_add(self):
        self.cli("--debug", "base", "--add", "Bar", "42", "0", "--size", "4096")
        assert "Bar-42.0" in self.cli("layout", "--bases").stdout

    def test_base_latest(self):
        self.cli("--debug", "base", "--add", "Bar", "42", "0", "--size", "4096")
        assert "Bar-42.0" in self.cli("base", "--latest").stdout

    def test_base_remove(self):
        self.cli("--debug", "base", "--add", "Bar", "42", "0", "--size", "4096")
        assert "Bar-42.0" in self.cli("base", "--latest").stdout

        self.cli("--debug", "base", "--remove", "Bar-42.0")
        assert "Bar-42.0" not in self.cli("base", "--latest").stdout

    def test_base_of_layer(self):
        self.cli("--debug", "base", "--add", "Image", "42", "0", "--size", "4096")
        assert "Image-42.0" in self.cli("base", "--latest").stdout

        self.cli("--debug", "layer", "--add")
        layers = self.cli("layout", "--layers").stdout
        assert "Image-42.1" in layers
        assert "Image-42.2" in layers
        assert "Image-42.3" not in layers

if __name__ == "__main__":
    unittest.main()

# vim: sw=4 et sts=4

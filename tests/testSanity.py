#!/usr/bin/env python
# vim: et ts=4 sw=4 sts=4

import unittest
import subprocess
import sys
import logging
from logging import debug
from mock import patch
from StringIO import StringIO
from collections import namedtuple

from fakelvm import FakeLVM
from imgbased import utils

from imgbased import CliApplication
import imgbased
import imgbased.lvm


class ImgbaseTestCase(unittest.TestCase):
    def autopart(self):
        vg = FakeLVM.VG("hostvg")
        vg._pvs = ["/dev/sda", "/dev/sdb"]
        FakeLVM._vgs = [vg]

        pool = FakeLVM.Thinpool()
        pool.vg_name = vg.vg_name
        pool.lv_name = "pool0"
        vg._lvs.add(pool)

        pool.create_thinvol("root", 10)

        # print(FakeLVM.lvs())

    def setUp(self):
        self.autopart()


class CliTestCase(ImgbaseTestCase):
    def cli(self, *args):
        debug("$ imgbased %s" % str(args))
        with \
                patch("imgbased.utils.subprocess"), \
                patch("imgbased.lvm.LVM", FakeLVM), \
                patch("imgbased.imgbase.LVM", FakeLVM), \
                patch("imgbased.imgbase.Hooks"), \
                patch("imgbased.imgbase.utils.Filesystem"), \
                patch("imgbased.imgbase.ImageLayers.current_layer",
                      lambda s: None):
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
        self.cli("--debug",
                 "layout",
                 "--init-nvr", "Image-1.0-0",
                 "--from", "hostvg/root")


class FindmntTestCase(CliTestCase):
    def test_findmnt(self):
        CliTestCase.assertIsNone(self,
                                 utils.findmnt(["SOURCE", "/tmp/_fake_dir_"]))

    def test_find_mount_target(self):
        CliTestCase.assertTrue(self, utils.find_mount_target())

    def test_find_mount_source(self):
        CliTestCase.assertIsNone(self,
                                 utils.find_mount_source("/tmp/_fake_dir_"))


class FilesystemTestCase(CliTestCase):
    def test_supported_filesystem(self):
        supported_fs = ['ext4', 'xfs']
        fs = utils.Filesystem.supported_filesystem()
        CliTestCase.assertEqual(self, supported_fs, fs)

    def test_get_type(self):
        with self.assertRaises(subprocess.CalledProcessError):
            # Command will fail because there is no _fake_vg_ to check
            CliTestCase.assertTrue(self, utils.Filesystem.get_type(
                                   "/dev/mapper/_fake_vg_"))

    def test_from_device(self):
        # Command will fail because there is no _fake_vg_ to check
        with self.assertRaises(subprocess.CalledProcessError):
            CliTestCase.assertTrue(self, utils.Filesystem.from_device(
                                   "/dev/mapper/_fake_vg_"))

    def test_from_mountpoint(self):
        with self.assertRaises(subprocess.CalledProcessError):
            # Command will fail because there is no _fake_mountpoint__ to check
            CliTestCase.assertTrue(self, utils.Filesystem.from_mountpoint(
                                   "/_fake_mountpoint_"))


class LayoutVerbTestCase(CliTestCase):
    def test_layout_init_from(self):
        debug("LVs: %s" % FakeLVM.lvs())
        lv_names = [lv.lv_name for lv in FakeLVM.list_lvs()]
        debug("LV Names: %s" % lv_names)
        assert "Image-1.0-0" in lv_names
        assert "Image-1.0-0+1" in lv_names

    def test_layout_bases(self):
        r = self.cli("--debug", "layout", "--bases")
        debug("Bases: %s" % r.stdout)
        assert r.stdout.strip() == "Image-1.0-0"

    def test_layout_layers(self):
        r = self.cli("--debug", "layout", "--layers")
        debug("Layers: %s" % r.stdout)
        assert r.stdout.strip() == "Image-1.0-0+1"


class BaseVerbTestCase(CliTestCase):
    def test_base_add(self):
        self.cli("--debug", "base", "--add", "Image-42-0",
                 "--size", "4096")
        print self.cli("layout", "--bases").stdout
        assert "Image-42-0" in self.cli("layout", "--bases").stdout

    def test_base_latest(self):
        self.cli("--debug", "base", "--add", "Image-42-0",
                 "--size", "4096")
        assert "Image-42-0" in self.cli("base", "--latest").stdout

    def test_base_remove(self):
        self.cli("--debug", "base", "--add", "Image-42-0",
                 "--size", "4096")
        assert "Image-42-0" in self.cli("base", "--latest").stdout

        self.cli("--debug", "base", "--remove", "Image-42-0")
        assert "Image-42-0" not in self.cli("base", "--latest").stdout

    def test_base_of_layer(self):
        self.cli("--debug", "base", "--add", "Image-42-0",
                 "--size", "4096")
        assert "Image-42-0" in self.cli("base", "--latest").stdout

        with self.assertRaises(imgbased.imgbase.LayerOutOfOrderError):
            # Exception, because we'd add a layer to a previous base, not the
            # latest
            self.cli("--debug", "layer", "--add")

        self.cli("--debug", "layer", "--add", "Image-42-0")
        layers = self.cli("layout", "--layers").stdout
        assert "Image-42-0+1" in layers

        self.cli("--debug", "layer", "--add")
        layers = self.cli("layout", "--layers").stdout
        assert "Image-42-0+2" in layers


class UpdateVerbTestCase(CliTestCase):
    def test_update(self):
        with patch("imgbased.plugins.update.LiveimgExtractor.extract") as mock:
            mock.return_value = ("Image-1.0-0", "Image-2.0-0")
            self.cli("--debug", "update", "/my/file")
            mock.assert_called_with("/my/file")


if __name__ == "__main__":
    unittest.main()

# vim: sw=4 et sts=4

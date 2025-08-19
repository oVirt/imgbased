#!/usr/bin/env python
# vim: et ts=4 sw=4 sts=4

import logging
import subprocess
import sys
from collections import namedtuple
from io import StringIO

import pytest
from fakelvm import FakeLVM
import imgbased
from imgbased import CliApplication, utils

log = logging.debug


class _StringIO(StringIO):
    def write(self, data):
        try:
            StringIO.write(self, data)
        except TypeError:
            StringIO.write(self, data.decode(errors="replace"))


@pytest.fixture
def setup_fake_lvm(cli_runner):
    vg = FakeLVM.VG("hostvg")
    vg._pvs = ["/dev/sda", "/dev/sdb"]
    FakeLVM._vgs = [vg]

    pool = FakeLVM.Thinpool()
    pool.vg_name = vg.vg_name
    pool.lv_name = "pool0"
    vg._lvs.add(pool)
    pool.create_thinvol("root", 10)

    cli_runner("--debug", "layout", "--init-nvr", "Image-1.0-0", "--from", "hostvg/root")

    return FakeLVM


@pytest.fixture
def cli_runner(mocker):
    def _runner(*args):
        mocker.patch("imgbased.utils.subprocess")
        mocker.patch("imgbased.command.subprocess")
        mocker.patch("imgbased.lvm.LVM", FakeLVM)
        mocker.patch("imgbased.imgbase.LVM", FakeLVM)
        mocker.patch("imgbased.imgbase.Hooks")
        mocker.patch("imgbased.imgbase.utils.Filesystem")
        mocker.patch("imgbased.imgbase.ImageLayers.current_layer", lambda s: None)

        oldout, olderr = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = _StringIO(), _StringIO()
        try:
            CliApplication(args)
            stdout, stderr = sys.stdout.getvalue(), sys.stderr.getvalue()
        except SystemExit as e:
            stdout, stderr = sys.stdout.getvalue(), sys.stderr.getvalue()
            if e.code != 0:
                logging.error(stderr)
                raise
        finally:
            sys.stdout, sys.stderr = oldout, olderr

        Retval = namedtuple("Returnvalues", ["stdout", "stderr"])
        return Retval(stdout, stderr)

    return _runner

# Utitlities Tests


def test_findmnt():
    assert utils.findmnt(["SOURCE", "/tmp/_fake_dir_"]) is None

def test_mount_target_returns_valid():
    """ Test if utils can find a valid mount target"""
    found_mounts = utils.find_mount_target()
    assert isinstance(found_mounts, list)
    assert found_mounts


def test_find_mount_source_returns_none_on_wrong_directory():
    """ Test if utils returns None when no mount source is found for a given directory"""
    assert utils.find_mount_source("/tmp/_fake_dir_") is None


def test_supported_filesystem():
    """ Test if utils returns a list of supported filesystems """
    supported_fs = ['ext4', 'xfs']
    fs = utils.Filesystem.supported_filesystem()
    assert fs == supported_fs


def test_get_type_raises():
    """ Test if utils.Filesystem.get_type raises an error when the device does not exist """
    with pytest.raises(subprocess.CalledProcessError):
        utils.Filesystem.get_type("/dev/mapper/_fake_vg_")


def test_from_device_raises():
    """" Subprocess returns errors on non-existing devices """
    with pytest.raises(subprocess.CalledProcessError):
        utils.Filesystem.from_device("/dev/mapper/_fake_vg_")


def test_from_mountpoint_raises():
    """ Subprocess returns errors on non-existing mountpoints """
    with pytest.raises(subprocess.CalledProcessError):
        utils.Filesystem.from_mountpoint("/_fake_mountpoint_")

# Layout Verb Tests


def test_layout_init_from(setup_fake_lvm):
    """ Test if the layout command initializes the base and layer images """
    lv_names = [lv.lv_name for lv in setup_fake_lvm.list_lvs()]
    assert "Image-1.0-0" in lv_names
    assert "Image-1.0-0+1" in lv_names


def test_layout_bases(cli_runner):
    """ Test if the layout command with bases param returns the base image name """
    r = cli_runner("--debug", "layout", "--bases")
    assert r.stdout.strip() == "Image-1.0-0"


def test_layout_layers(cli_runner):
    """ Test if the layout command with layers param returns the layer image name """
    r = cli_runner("--debug", "layout", "--layers")
    assert r.stdout.strip() == "Image-1.0-0+1"

# Base Verb Tests


def test_base_add(cli_runner):
    """ Test if the base command with add param adds it to the list of bases """
    cli_runner("--debug", "base", "--add", "Image-42-0", "--size", "4096")
    r = cli_runner("layout", "--bases")
    assert "Image-42-0" in r.stdout.strip()


def test_base_latest_returns_newly_added(cli_runner):
    """ Test if the base command with latest param returns the latest base image """
    r = cli_runner("base", "--latest")
    assert r.stdout.strip() == "Image-42-0"


def test_base_remove(cli_runner):
    cli_runner("--debug", "base", "--remove", "Image-42-0")
    r = cli_runner("layout", "--bases")
    assert "Image-42-0" not in r.stdout.strip()


def test_base_of_layer(cli_runner):
    cli_runner("--debug", "base", "--add", "Image-42-0", "--size", "4096")

    with pytest.raises(imgbased.imgbase.LayerOutOfOrderError):
        cli_runner("--debug", "layer", "--add")

    cli_runner("--debug", "layer", "--add", "Image-42-0")
    layers = cli_runner("layout", "--layers").stdout
    assert "Image-42-0+1" in layers.strip()

    cli_runner("--debug", "layer", "--add")
    layers = cli_runner("layout", "--layers").stdout
    assert "Image-42-0+2" in layers.strip()

# Update verb tests


def test_update(cli_runner, mocker):
    mock_extract = mocker.patch("imgbased.plugins.update.LiveimgExtractor.extract")
    mock_extract.return_value = ("Image-1.0-0", "Image-2.0-0")

    cli_runner("--debug", "update", "/my/file")

    mock_extract.assert_called_once_with("/my/file")

# vim: sw=4 et sts=4

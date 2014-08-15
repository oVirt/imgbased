#!/usr/bin/env python

import unittest
import sh
import logging


# Increase the capture length of python-sh to show complete errors
sh.ErrorReturnCode.truncate_cap = 999999

log = logging.info


class TestSanity(unittest.TestCase):
    def test_imgbase(self):
        from sh import imgbase, lvm

        log("Using %s" % imgbase)
        log(imgbase("--version"))

        log("Existing LVM layout")
        log(lvm.pvs())
        log(lvm.vgs())
        log(lvm.lvs())

        assert "HostVG" in lvm.vgs()

        # All subsequent imgbase calls include the debug arg
        imgbase = imgbase.bake("--debug")

        assert "Image-0.0" in imgbase.layout()

        log(imgbase.layer("--add"))
        assert "Image-0.1" in imgbase.layout()

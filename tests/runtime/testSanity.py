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

        log("Existing LVM layout")
        log(lvm.pvs())
        log(lvm.vgs())
        log(lvm.lvs())

        assert "Image-0.0" in imgbase.layout()

        imgbase.layer("--add")
        assert "Image-0.1" in imgbase.layout()

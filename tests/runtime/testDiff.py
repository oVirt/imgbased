#!/usr/bin/env python
# vim: et ts=4 sw=4 sts=4

import logging
import unittest
import sh


# Increase the capture length of python-sh to show complete errors
sh.ErrorReturnCode.truncate_cap = 999999

log = logging.info


class TestDiff(unittest.TestCase):
    def test_basic(self):
        from sh import imgbase, touch

        # All subsequent imgbase calls include the debug arg
        imgbase = imgbase.bake("--debug")

        assert "Image-0.0" in imgbase.layout()
        assert "Image-0.1" in imgbase.layout()

        log(imgbase.layer("--add"))
        assert "Image-0.2" in imgbase.layer("--latest")

        touch("/root/marker")
        touch("/var/tmp/marker")
        diff = imgbase("--debug", "diff", "Image-0.1", "Image-0.2")
        print(diff)
        assert "/root/marker" in diff
        assert "/var/tmp/marker" not in diff

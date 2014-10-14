#!/usr/bin/env python
# vim: et ts=4 sw=4 sts=4

import unittest
import sh
import logging
import glob


# Increase the capture length of python-sh to show complete errors
sh.ErrorReturnCode.truncate_cap = 999999

log = logging.info


class TestImgbased(unittest.TestCase):
    def test_imgbase(self):
        from sh import imgbase, lvm, touch

        # All subsequent imgbase calls include the debug arg
        imgbase = imgbase.bake("--debug")

        log("Using %s" % imgbase)
        log(imgbase("--version"))

        log("Existing LVM layout")
        log(lvm.pvs())
        log(lvm.vgs())
        log(lvm.lvs())

        assert "HostVG" in lvm.vgs()

        assert "Image-0.0" in imgbase.layout()

        log(imgbase.layer("--add"))
        assert "Image-0.1" in imgbase.layout()

        touch("/var/tmp/marker")
        diff = imgbase("--debug", "diff", "Image-0.0", "Image-0.1")
        print diff
        assert "/var/tmp/marker" in diff

    def test_fstrim(self, use_autodiscard=False, num_trials=2, max_delta=0.05):
        # FIXME improve by splitting into several test cases
        from sh import imgbase, dd, sleep, rm, ls

        imgbase = imgbase.bake("--debug")
        img_free = lambda: float(imgbase("layout", "--free-space"))

        def trials(num_bins=1, size_bin=500):
            for N in xrange(0, num_trials):
                a = img_free()

                for B in xrange(0, num_bins):
                    dd("if=/dev/zero", "of=/var/tmp/%s.bin" % N, "bs=1M",
                       "count=%d" % size_bin)

                print (ls("-shal", *glob.glob("/var/tmp/*.bin")))
                b = img_free()

                rm("-f", "/var/tmp/*.bin")

                if use_autodiscard:
                    print("We are testing the auto-discard " +
                          "functionality of the fs")
                    sleep("10")
                else:
                    from sh import fstrim
                    fstrim("-v", "/")

                c = img_free()

                ratio = a / c

                print(a, b, c, ratio)

                assert ratio > (1.0 - max_delta), \
                    "Delta is larger than %s" % max_delta

        trials(1, 100)
        trials(100, 1)

    def test_discard(self):
        return self.test_fstrim(use_autodiscard=True)


class TestEnvironment(unittest.TestCase):
    def test_selinux_denials(self):
        """Looking for SELinux AVC denials
        """
        from sh import getenforce
        assert getenforce().strip() == "Enforcing"
        # assert not grep("denied", "/var/log/audit.log")

    def test_relevant_packages(self):
        """Looking for mandatory packages
        """
        from sh import which
        for app in ["df", "du", "diff", "lvm"]:
            assert which(app)

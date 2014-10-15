#!/usr/bin/env python
# vim: et ts=4 sw=4 sts=4

import unittest
import sh
import logging
import glob


# Increase the capture length of python-sh to show complete errors
sh.ErrorReturnCode.truncate_cap = 999999

log = logging.info


def dd(N, count=100):
    from sh import dd
    dd("if=/dev/zero", "of=/var/tmp/%s.bin" % N, "bs=1M",
       "count=%d" % count)


def trial(num_bins=1, size_bin=500, after_rm=None, max_delta=0.05):
    from sh import imgbase, rm, ls

    imgbase = imgbase.bake("--debug")
    img_free = lambda: float(imgbase("layout", "--free-space"))

    a = img_free()

    [dd(B, size_bin) for B in xrange(0, num_bins)]
    print (ls("-shal", *glob.glob("/var/tmp/*.bin")))
    b = img_free()

    rm("-f", "/var/tmp/*.bin")
    after_rm()
    c = img_free()

    ratio = a / c
    print(a, b, c, ratio)
    delta = 1 - ratio
    assert delta < max_delta, \
        "Delta %s is larger than %s" % (delta, max_delta)


class TestFS(unittest.TestCase):
    def test_fstrim(self, count=1, size=100):
        # FIXME improve by splitting into several test cases

        def after_rm():
            from sh import fstrim
            fstrim("-v", "/")

        trial(count, size, after_rm)

    def test_fstrim_many(self):
        self.test_fstrim(100, 1)

    def test_discard(self, count=1, size=100):
        def after_rm():
            from sh import sleep
            print("We are testing the auto-discard " +
                  "functionality of the fs")
            sleep("10")

        trial(count, size, after_rm)

    def test_discard_many(self):
        self.test_discard(100, 1)

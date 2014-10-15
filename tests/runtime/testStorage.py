#!/usr/bin/env python
# vim: et ts=4 sw=4 sts=4

import unittest
import sh
import logging
import glob


# Increase the capture length of python-sh to show complete errors
sh.ErrorReturnCode.truncate_cap = 999999

log = logging.info


class TestFS(unittest.TestCase):
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

                delta = 1 - ratio
                assert delta > max_delta, \
                    "Delta %s is larger than %s" % (delta, max_delta)

        trials(1, 100)
        trials(100, 1)

    def test_discard(self):
        return self.test_fstrim(use_autodiscard=True)

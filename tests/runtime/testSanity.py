#!/usr/bin/env python

import unittest


class TestSanity(unittest.TestCase):
    def test_imgbase(self):
        from sh import imgbase

        assert "Image-0.0" in imgbase.layout()

        imgbase.layer("--add")
        assert "Image-0.1" in imgbase.layout()

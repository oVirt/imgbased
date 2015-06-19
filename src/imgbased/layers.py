#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# imgbase
#
# Copyright (C) 2015  Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Author(s): Fabian Deutsch <fabiand@redhat.com>
#

import logging

log = logging.getLogger(__package__)

from .lvm import LVM
from .utils import memoize


class Image(object):
    vg = None

    nvr_fmt = "%s-%s.%s"
    name = None
    version = None
    release = None
    layers = None

    @property
    def nvr(self):
        return self.nvr_fmt % (self.name, self.version, self.release)

    @property
    @memoize
    def path(self):
        return self.lvm.path

    @property
    def lvm(self):
        return LVM.LV(self.vg(), self.nvr)

    @property
    def version_release(self):
        return (int(self.version), int(self.release))

    def __init__(self, vg=None, name=None, version=None, release=None):
        self.vg = vg
        self.name = name or self.name
        self.version = version
        self.release = release
        self.layers = []

    def __str__(self):
        return self.nvr

    def __repr__(self):
        return "<%s %s/>" % (self, self.layers or "")

    def is_base(self):
        return int(self.release) == 0

    def is_layer(self):
        return not self.is_base()

    def __lt__(self, other):
        """
        >>> a = Image(None, "Image", 1, 0)
        >>> b = Image(None, "Image", 2, 0)
        >>> a < b
        True
        >>> a == b
        False
        >>> a > b
        False
        """
        return self.version_release < other.version_release

    def __eq__(self, other):
        """
        >>> a = Image(None, "Image", 1, 0)
        >>> b = Image(None, "Image", 2, 0)
        >>> a == b
        False

        >>> c = Image(None, "Image", 1, 1)
        >>> d = Image(None, "Image", 21, 0)
        >>> e = Image(None, "Image", 11, 0)
        >>> sorted([a, b, c, d, e])
        [<Image-1.0 />, <Image-1.1 />, <Image-2.0 />, <Image-11.0 />, \
<Image-21.0 />]

        >>> a = Image(None, "Image", 2, 0)
        >>> a == b
        True
        """
        # FIXME check type
        return repr(self) == repr(other)


class Base(Image):
    def protect(self):
        self.lvm.permission("r")
        self.lvm.setactivationskip(True)
        self.lvm.activate(False, True)

    def unprotect(self):
        self.lvm.permission("rw")
        self.lvm.setactivationskip(False)
        self.lvm.activate(True, True)

    def unprotected(self):
        this = self

        class UnprotectedBase(object):
            base = this

            def __enter__(self):
                self.base.unprotect()

            def __exit__(self, exc_type, exc_value, tb):
                self.base.protect()
        return UnprotectedBase()

# vim: sw=4 et sts=4:

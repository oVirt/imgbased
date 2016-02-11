#!/usr/bin/python
# -*- coding: utf-8 -*-
#
#
#
# Copyright (C) 2014  Red Hat, Inc.
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
import os
from .utils import File, grub2_set_default


log = logging.getLogger(__package__)


class Bootloader(object):
    dry = False

    def set_default(self, key):
        """
        """
        raise NotImplementedError()

    def add_entry(self, key, title, linux, initramfs, append):
        """Add a boot entry to the bootloader, and make it the default
        """
        raise NotImplementedError()

    def remove_entry(self, key):
        """Remove a boot entry to the bootloader
        """
        raise NotImplementedError()


class BlsBootloader(Bootloader):
    """Fixme can probably use new-kernel-pkg
    """
    bls_dir = "/boot/loader/entries"

    def _efile(self, key):
        return File(os.path.join(self.bls_dir, "%s.conf" % key))

    def add_entry(self, key, title, linux, initramfs, append):
        edir = self.bls_dir

        if not os.path.isdir(edir):
            os.makedirs(edir)

        entry = ["title %s" % title,
                 "linux /%s" % linux,
                 "initrd /%s" % initramfs,
                 "options %s" % append]

        log.debug("Entry: %s" % entry)

        if not self.dry:
            efile = self._efile(key)
            efile.writen("\n".join(entry))

        return key

    def remove_entry(self, key):
        f = self._efile(key)
        log.debug("Removing boot entry: %s" % f.contents)
        f.remove()

    def _key_val(self, key):
        kvs = dict()
        for line in self._efile(key).lines():
            k, sep, v = line.partition(" ")
            kvs[k] = v
        return kvs

    def set_default(self, key):
        title = self._key_val(key)["title"]
        log.debug("Making default: %s" % title)
        grub2_set_default(title)

# vim: sw=4 et sts=4:

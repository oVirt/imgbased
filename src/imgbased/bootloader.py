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
from .utils import File, ExternalBinary


log = logging.getLogger(__package__)


def grub2_set_default(key):
    ExternalBinary().grub2_set_default([key])


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


class SyslinuxBootloader(Bootloader):
    config_file = "/boot/syslinux.cfg"

    def _config(self):
        cfg = File(self.config_file)
        if cfg.exists():
            return cfg.contents.splitlines()
        else:
            return []

    def _get_key(self, k, default):
        candidate = default
        candidates = [e for e in self._config()
                      if e.startswith("%s " % k)]
        assert len(candidates) < 2
        if candidates:
            candidate = candidates.pop()
        return candidate

    def get_default(self):
        return self._get_key("DEFAULT", None)

    def get_timeout(self):
        return self._get_key("TIMEOUT", None)

    def set_default(self, title):
        """
        >>> import tempfile
        >>> b = SyslinuxBootloader()
        >>> _, b.config_file = tempfile.mkstemp()

        >>> b.add_entry("<name>", "<kernel>", "<initramfs>", "<append>")
        >>> b.set_default("<name>")

        >>> print("\\n".join(b._config()))
        DEFAULT <name>
        TIMEOUT 300
        <BLANKLINE>
        LABEL <name>
          SAY Booting '<name>' ...
          KERNEL <kernel>
          INITRD <initramfs>
          APPEND <append>
        """
        entries = self._config()

        # Drop old default
        entries = [e for e in entries if not e.startswith("DEFAULT ")]
        # Set new default
        entries.insert(0, "DEFAULT %s" % title)

        self._save(entries)

    def add_entry(self, title, linux, initramfs, append):
        """
        >>> import tempfile
        >>> b = SyslinuxBootloader()
        >>> _, b.config_file = tempfile.mkstemp()

        >>> b.add_entry("<name>", "<kernel>", "<initramfs>", "<append>")

        >>> print("\\n".join(b._config()))
        TIMEOUT 300
        <BLANKLINE>
        LABEL <name>
          SAY Booting '<name>' ...
          KERNEL <kernel>
          INITRD <initramfs>
          APPEND <append>

        >>> b.add_entry("<name1>", "<kernel>", "<initramfs>", "<append>")

        >>> print("\\n".join(b._config()))
        TIMEOUT 300
        <BLANKLINE>
        LABEL <name>
          SAY Booting '<name>' ...
          KERNEL <kernel>
          INITRD <initramfs>
          APPEND <append>
        <BLANKLINE>
        LABEL <name1>
          SAY Booting '<name1>' ...
          KERNEL <kernel>
          INITRD <initramfs>
          APPEND <append>

        >>> os.unlink(b.config_file)
        """

        entry = ["",
                 "LABEL %s" % title,
                 "  SAY Booting '%s' ..." % title,
                 "  KERNEL %s" % linux,
                 "  INITRD %s" % initramfs,
                 "  APPEND %s" % append]

        log.debug("Entry: %s" % entry)

        entries = self._config()
        entries += entry

        # Set some timeout, otherwise it's 0
        if not self.get_timeout():
            entries.insert(0, "TIMEOUT 300")

        self._save(entries)

    def _save(self, entries):
        if not self.dry:
            # Write the new config
            File(self.config_file).writen("\n".join(entries), "w+")


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

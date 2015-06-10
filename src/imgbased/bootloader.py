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


log = logging.getLogger(__package__)


class Bootloader(object):
    dry = False

    def add_entry(self, title, linux, initramfs, append):
        """Add a boot entry to the bootloader, and make it the default
        """
        raise NotImplementedError()


class SyslinuxBootloader(Bootloader):
    config_file = "/boot/syslinux.cfg"

    def _config(self):
        with open(self.config_file) as src:
            return src.read().splitlines()

    def add_entry(self, title, linux, initramfs, append):
        """
        >>> import tempfile
        >>> b = SyslinuxBootloader()
        >>> _, b.config_file = tempfile.mkstemp()

        >>> b.add_entry("<name>", "<kernel>", "<initramfs>", "<append>")

        >>> print("\\n".join(b._config()))
        DEFAULT '<name>'
        <BLANKLINE>
        LABEL '<name>'
          SAY Booting '<name>' ...
          KERNEL <kernel>
          INITRD <initramfs>
          APPEND <append>

        >>> b.add_entry("<name1>", "<kernel>", "<initramfs>", "<append>")

        >>> print("\\n".join(b._config()))
        DEFAULT '<name1>'
        <BLANKLINE>
        LABEL '<name>'
          SAY Booting '<name>' ...
          KERNEL <kernel>
          INITRD <initramfs>
          APPEND <append>
        <BLANKLINE>
        LABEL '<name1>'
          SAY Booting '<name1>' ...
          KERNEL <kernel>
          INITRD <initramfs>
          APPEND <append>

        >>> os.unlink(b.config_file)
        """

        entry = ["",
                 "LABEL '%s'" % title,
                 "  SAY Booting '%s' ..." % title,
                 "  KERNEL %s" % linux,
                 "  INITRD %s" % initramfs,
                 "  APPEND %s" % append]

        log.debug("Entry: %s" % entry)

        entries = self._config()
        entries += entry

        # Drop old default
        entries = [e for e in entries if not e.startswith("DEFAULT ")]
        # Set new default
        entries.insert(0, "DEFAULT '%s'" % title)

        if not self.dry:
            # Write the new config
            with open(self.config_file, "w+") as dst:
                dst.write("\n".join(entries + [""]))


def uuid():
    with open("/proc/sys/kernel/random/uuid") as src:
        return src.read().replace("-", "").strip()


class BlsBootloader(Bootloader):
    """Fixme can probably use new-kernel-pkg
    """
    bls_dir = "/boot/loader/entries"

    def add_entry(self, title, linux, initramfs, append):
        eid = uuid()
        edir = self.bls_dir

        if not os.path.isdir(edir):
            os.makedirs(edir)

        efile = os.path.join(edir, "%s.conf" % eid)

        entry = ["title %s" % title,
                 "linux /%s" % linux,
                 "initrd /%s" % initramfs,
                 "options %s" % append]

        log.debug("Entry: %s" % entry)
        if not self.dry:
            with open(efile, "w+") as dst:
                dst.write("\n".join(entry))

# vim: sw=4 et sts=4:

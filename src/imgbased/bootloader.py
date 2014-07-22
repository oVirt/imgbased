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
log = logging.getLogger("imgbase")
import os
import glob


class Bootloader(object):
    p = None

    def __init__(self, p):
        self.p = p

    def _glob_boot(self, pat):
        g = sorted(glob.glob("/boot/%s" % pat))[-1]
        return os.path.basename(g)

    def _kernel(self):
        return self._glob_boot("vmlinuz-*.x86_64")

    def _initramfs(self):
        return self._glob_boot("initramfs-*.x86_64.img")

    def _append(self, name, rootlv):
        args = {"name": name, "rootlv": rootlv}
        return "rd.lvm.lv={name} root={rootlv} console=ttyS0".format(**args)

    def add_boot_entry(self, name, rootlv):
        """Add a boot entry to the bootloader, and make it the default
        """
        raise NotImplementedError()


class SyslinuxBootloader(Bootloader):
    config_file = "/boot/syslinux.cfg"

    def _config(self):
        with open(self.config_file) as src:
            return src.read().splitlines()

    def add_boot_entry(self, name, rootlv):
        """
        >>> import tempfile
        >>> b = SyslinuxBootloader(None)

        # A bit of mockup
        >>> b._kernel = lambda: "<kernel>"
        >>> b._initramfs = lambda: "<initramfs>"
        >>> _, b.config_file = tempfile.mkstemp()

        >>> b.add_boot_entry("<name>", "<rootlv>")

        >>> print("\\n".join(b._config()))
        DEFAULT '<name>'
        <BLANKLINE>
        LABEL '<name>'
          SAY Booting '<name>' ...
          KERNEL <kernel>
          INITRD <initramfs>
          APPEND rd.lvm.lv=<name> root=<rootlv> console=ttyS0

        >>> b.add_boot_entry("<name1>", "<rootlv>")

        >>> print("\\n".join(b._config()))
        DEFAULT '<name1>'
        <BLANKLINE>
        LABEL '<name>'
          SAY Booting '<name>' ...
          KERNEL <kernel>
          INITRD <initramfs>
          APPEND rd.lvm.lv=<name> root=<rootlv> console=ttyS0
        <BLANKLINE>
        LABEL '<name1>'
          SAY Booting '<name1>' ...
          KERNEL <kernel>
          INITRD <initramfs>
          APPEND rd.lvm.lv=<name1> root=<rootlv> console=ttyS0

        >>> os.unlink(b.config_file)
        """

        linux = self._kernel()
        initramfs = self._initramfs()
        append = self._append(name, rootlv)

        entry = ["",
                 "LABEL '%s'" % name,
                 "  SAY Booting '%s' ..." % name,
                 "  KERNEL %s" % linux,
                 "  INITRD %s" % initramfs,
                 "  APPEND %s" % append]

        log.debug("Entry: %s" % entry)

        entries = self._config()
        entries += entry

        # Drop old default
        entries = [e for e in entries if not e.startswith("DEFAULT ")]
        # Set new default
        entries.insert(0, "DEFAULT '%s'" % name)

        if not self.p or not self.p.dry:
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

    def add_boot_entry(self, name, rootlv):
        # FIXME this is missing the make-default part (not possible with bls)
        eid = uuid()
        edir = self.bls_dir

        if not os.path.isdir(edir):
            os.makedirs(edir)

        efile = os.path.join(edir, "%s.conf" % eid)

        linux = self._kernel()
        initramfs = self._initramfs()
        append = self._append(name, rootlv)

        entry = ["title %s" % name,
                 "linux /%s" % linux,
                 "initrd /%s" % initramfs,
                 "options %s" % append]

        log.debug("Entry: %s" % entry)
        if not self.p or not self.p.dry:
            with open(efile, "w+") as dst:
                dst.write("\n".join(entry))

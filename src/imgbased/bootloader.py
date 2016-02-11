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
import re
from .utils import grubby


log = logging.getLogger(__package__)


class BootloaderError(Exception):
    pass


class NoKeyFoundError(BootloaderError):
    pass


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


class Grubby(Bootloader):
    """This class can do bootloader configuration by using grubby
    """
    _keyarg = "img.bootid"

    class GrubbyEntry(object):
        """Simple class to parse out grubby entries
        >>> entry = '''index=0
        ... kernel=/boot/ovirt-node-4.0+1/vmlinuz-3.10.0-327.4.5.el7.x86_64
        ... args="ro crashkernel=auto rd.lvm.lv=centos_installed/root \
        ... rd.lvm.lv=centos_installed/swap rhgb quiet LANG=en_US.UTF-8"
        ... root=/dev/mapper/centos_installed-root
        ... initrd=\
        ... /boot/ovirt-node-4.0+1/initramfs-3.10.0-327.4.5.el7.x86_64.img
        ... title=ovirt-node-4.0+1'''

        >>> parsed = Grubby.GrubbyEntry.parse(entry)
        >>> parsed.title
        'ovirt-node-4.0+1'
        >>> parsed.root
        '/dev/mapper/centos_installed-root'

        >>> entry = '''index=2
        ... kernel=/boot/vmlinuz-4.0.0.fc23.x86_64
        ... args="ro console=ttyS0"
        ... root=/dev/sda3
        ... initrd=/boot/initramfs-4.0.0.fc23.x86_64.img
        ... title=dummy'''

        >>> parsed = Grubby.GrubbyEntry.parse(entry)
        >>> parsed.kernel
        '/boot/vmlinuz-4.0.0.fc23.x86_64'
        >>> parsed.initrd
        '/boot/initramfs-4.0.0.fc23.x86_64.img'

        >>> entry = '''index=1
        ... non linux entry'''
        >>> parsed = Grubby.GrubbyEntry.parse(entry)
        >>> parsed.title
        'non linux entry'
        >>> assert parsed.kernel == None
        """

        args = None
        root = None
        index = None
        title = None
        kernel = None
        initrd = None

        @staticmethod
        def parse(entry):
            g = Grubby.GrubbyEntry()

            r = re.compile(r"""(?:index=)(\d+)\n?
                               (?:(?:kernel=)?(.*?)\n)?
                               (?:(?:args=)?(.*?)\n)?
                               (?:(?:root=)?(.*?)\n)?
                               (?:(?:initrd=)?(.*?)\n)?
                               (?:(?:title=)?(.*))?
                            """, re.VERBOSE)
            matches = r.match(entry)
            g.index, g.kernel, g.args, g.root, g.initrd, g.title = \
                matches.groups()
            return g

    def _parse_key_from_args(self, args):
        matches = re.findall("%s=([^\s]+)" % self._keyarg, args)
        if len(matches) == 0:
            raise NoKeyFoundError()
        return matches[0]

    def _get_entries(self):
        r = re.compile(r'(index.*?)(?=index)', re.DOTALL)
        stanzas = filter(None, r.split(grubby("--info=ALL")))

        entries = (self.GrubbyEntry.parse(stanza) for stanza in stanzas)

        entrymap = {}
        for entry in entries:
            try:
                key = self._parse_key_from_args(entry.args)
            except NoKeyFoundError:
                log.debub("No key found in entry: %s" % entry.args)
                continue

            entrymap[key] = entry

        return entrymap

    def add_entry(self, key, title, linux, initramfs, append):
        log.debug("Adding entry: %s" % key)

        assert " " not in key
        keyarg = " %s=%s" % (self._keyarg, key)
        append += keyarg

        grubby("--add-kernel", "/boot/%s" % linux,
               "--initrd", "/boot/%s" % initramfs,
               "--args", append,
               "--title", title)

        return key

    def remove_entry(self, key):
        entry = self._get_entries()[key]
        log.debug("Removing boot entry: %s" % entry.title)
        grubby("--remove-kernel", entry.kernel)

    def set_default(self, key):
        entry = self._get_entries()[key]
        log.debug("Making default: %s" % entry.title)
        grubby("--set-default", entry.kernel)

# vim: sw=4 et sts=4:

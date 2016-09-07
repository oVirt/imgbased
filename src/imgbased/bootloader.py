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
import re
import shutil
from .utils import grubby
from .naming import Layer


log = logging.getLogger(__package__)


class BootloaderError(Exception):
    pass


class InvalidBootEntryError(BootloaderError):
    pass


class NoKeyFoundError(BootloaderError):
    pass


class Bootloader(object):
    """Low-level object to access the bootloader
    """
    dry = False

    def list(self):
        raise NotImplementedError()

    def set_default(self, key):
        """
        """
        raise NotImplementedError()

    def get_default(self):
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
        >>> parsed.args
        '"ro console=ttyS0"'

        >>> entry = '''index=1
        ... non linux entry'''
        >>> parsed = Grubby.GrubbyEntry.parse(entry)
        Traceback (most recent call last):
        ...
        InvalidBootEntryError

        >>> entries = '''index=0
        ... kernel=ker0
        ... args=ar0 img.bootid=0
        ... initrd=in0
        ... title=tit0
        ... index=1
        ... kernel=ker1
        ... args=ar1
        ... initrd=in1
        ... title=tit1
        ... index=4
        ... non linux entry'''

        There will be only one entry, because only one has a key
        >>> valid, other = Grubby()._parse_entries(entries)
        >>> len(valid)
        1
        >>> len(other)
        1
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

            if not all([g.kernel, g.args, g.initrd]):
                raise InvalidBootEntryError()

            return g

    def _parse_key_from_args(self, args):
        """
        >>> g = Grubby()
        >>> g._parse_key_from_args("rhgb crashkernel=auto "
        ... "rd.lvm.lv=onn/ovirt-node-ng-4.0.0-0.0.master.20160211.0.el7+1 "
        ... "quiet rd.lvm.lv=onn/swap img.bootid=ovirt-node-ng-4.0.0"
        ... "-0.0.master.20160211.0.el7+1")
        'ovirt-node-ng-4.0.0-0.0.master.20160211.0.el7+1'
        """
        log.debug("Finding key in args: %s" % args)
        matches = re.findall("%s=([^\s\"']+)" % self._keyarg, args)
        if len(matches) == 0:
            raise NoKeyFoundError()
        return matches[0]

    def _get_valid_entries(self):
        return self._parse_entries(grubby("--info=ALL"))[0]

    def _get_other_entries(self):
        return self._parse_entries(grubby("--info=ALL"))[1]

    def _parse_entries(self, data):
        """Returns (valid_entries_map, other_entires_list)
        """
        r = re.compile(r'(index.*?)(?=index)', re.DOTALL)
        stanzas = filter(None, r.split(data))

        entrymap = {}
        other_entries = []
        for stanza in stanzas:
            try:
                entry = self.GrubbyEntry.parse(stanza)
                key = self._parse_key_from_args(entry.args)
            except InvalidBootEntryError:
                log.debug("Failed to parse entry: %s" % stanza)
                continue
            except NoKeyFoundError:
                log.debug("No key found in entry: %s" % entry.args)
                other_entries.append(entry)
                continue

            entrymap[key] = entry

        log.debug("Found valid entries: %s" % entrymap)

        return (entrymap, other_entries)

    def add_entry(self, key, title, linux, initramfs, append):
        log.debug("Adding entry: %s" % key)

        assert " " not in key
        keyarg = " %s=%s" % (self._keyarg, key)
        append += keyarg

        grubby("--copy-default",
               "--add-kernel", "/boot/%s" % linux,
               "--initrd", "/boot/%s" % initramfs,
               "--args", append,
               "--title", title)

        return key

    def remove_entry(self, key):
        entry = self._get_valid_entries()[key]
        log.debug("Removing boot entry: %s" % entry.title)
        log.info("Removing boot entry: %s" % entry.title)
        grubby("--remove-kernel", entry.kernel)

    def set_default(self, key):
        entry = self._get_valid_entries()[key]
        log.debug("Making default: %s" % entry.title)
        grubby("--set-default", entry.kernel)

    def get_default(self):
        log.debug("Getting default")
        kernel = grubby("--default-kernel")
        entries = self._get_valid_entries()
        entry = [e for e in entries if entries[e].kernel == kernel][0]
        log.debug("Default: %s" % entry)
        return entry

    def list(self):
        return self._get_valid_entries()

    def list_other(self):
        return self._get_other_entries()

    def _backup(self):
        # The links in /etc are relative for some reason...
        os.chdir("/")

        path = None
        paths = ["/etc/grub2.cfg", "/etc/grub2-efi.cfg"]

        for p in paths:
            if os.path.exists(p):
                path = os.path.abspath(os.readlink(p))
                break

        log.info("Backing up the grub configuration")
        log.debug("Copying %s to %s" % (path, path+".bak"))
        shutil.copy2(path, path + ".bak")

    def remove_other_entries(self):
        log.info("Removing other boot entries")
        self._backup()
        entries = self._get_other_entries()
        for e in entries:
            log.debug("Removing other boot entry: %s" % e.title)
            grubby("--remove-kernel", e.kernel)


class BootConfiguration():
    """High-Level image centric boot configuration
    """

    bootloader = None

    def __init__(self):
        self.bootloader = Grubby()

    def _key_from_layer(self, layer):
        if not type(layer) is Layer:
            raise BootloaderError("Boot entries can only be added for "
                                  "layers, got %r" % layer)
        key = layer.lv_name
        assert " " not in key
        return key

    def list(self):
        return self.bootloader.list()

    def list_other(self):
        return self.bootloader.list_other()

    def add(self, layer, title,  vmlinuz, initrd, append):
        key = self._key_from_layer(layer)
        return self.bootloader.add_entry(key, title, vmlinuz, initrd, append)

    def remove(self, layer):
        key = self._key_from_layer(layer)
        return self.bootloader.remove(key)

    def remove_other_entries(self):
        return self.bootloader.remove_other_entries()

    def set_default(self, layer):
        key = self._key_from_layer(layer)
        return self.bootloader.set_default(key)

    def get_default(self):
        return self.bootloader.get_default()

# vim: sw=4 et sts=4:

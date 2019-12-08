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
import glob
import logging
import operator
import os
import re
import shutil
import tempfile

from .naming import Layer
from .utils import (File, ShellVarFile, find_mount_target, grub2_editenv,
                    grub2_mkconfig, grub_cfg_path, grubby)

log = logging.getLogger(__package__)


class BootloaderError(Exception):
    pass


class InvalidBootEntryError(BootloaderError):
    pass


class NoKeyFoundError(BootloaderError):
    pass


class BootPartitionRequires1G(BootloaderError):
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
    _DEVNULL = open(os.devnull, 'w')

    class GrubbyEntry(object):
        """Simple class to parse out grubby entries
        >>> entry = '''index=0
        ... kernel=/boot/ovirt-node-4.0+1/vmlinuz-3.10.0-327.4.5.el7.x86_64
        ... args="ro crashkernel=auto rd.lvm.lv=centos_installed/root \
        ... rd.lvm.lv=centos_installed/swap rhgb quiet LANG=en_US.UTF-8"
        ... root=/dev/mapper/centos_installed-root
        ... initrd=\
        ... /boot/ovirt-node-4.0+1/initramfs-3.10.0-327.4.5.el7.x86_64.img
        ... title=ovirt-node-4.0+1 (3.10.0-327.4.5.el7.x86_64)
        ... id="my-custom-bls-id"'''

        >>> parsed = Grubby.GrubbyEntry.parse(entry)
        >>> parsed.title
        'ovirt-node-4.0+1 (3.10.0-327.4.5.el7.x86_64)'
        >>> parsed.blsid
        'my-custom-bls-id'
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
        'ro console=ttyS0'
        >>> parsed.blsid
        ''

        >>> entry = '''index=1
        ... non linux entry'''
        >>> parsed = Grubby.GrubbyEntry.parse(entry)
        Traceback (most recent call last):
        ...
        imgbased.bootloader.InvalidBootEntryError

        >>> entries = '''index=0
        ... kernel=ker0
        ... args=ar0 img.bootid=0
        ... root=foo0
        ... initrd=in0
        ... title=node
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

        blsid = None
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
                               (?:(?:title=)?(.*)\n?)?
                               (?:(?:id=)?(.*))?
                            """, re.VERBOSE)
            matches = r.match(entry)
            g.index, g.kernel, g.args, g.root, g.initrd, g.title, g.blsid = \
                [x.strip('"') if x else x for x in matches.groups()]

            if not all([g.kernel, g.args, g.initrd]):
                raise InvalidBootEntryError()

            return g

        def bls_conf_path(self):
            if not self.blsid:
                raise RuntimeError("Missing bls id for %s" % self)
            return "/boot/loader/entries/%s.conf" % self.blsid

    def __init__(self, use_bls=None):
        Bootloader.__init__(self)
        if use_bls is None:
            self._use_bls = os.access("/usr/libexec/grubby/grubby-bls",
                                      os.X_OK)
        else:
            self._use_bls = use_bls

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
        matches = re.findall("%s=([^\\s\"']+)" % self._keyarg, args)
        if len(matches) == 0:
            raise NoKeyFoundError()
        return matches[0]

    def _get_valid_entries(self):
        return self._parse_entries(grubby("--info=ALL",
                                          stderr=self._DEVNULL))[0]

    def _get_other_entries(self):
        return self._parse_entries(grubby("--info=ALL",
                                          stderr=self._DEVNULL))[1]

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
                if "node" not in entry.title and "rhvh" not in entry.title:
                    raise NoKeyFoundError()
                key = self._parse_key_from_args(entry.args)
            except InvalidBootEntryError:
                log.debug("Failed to parse entry: %s" % stanza)
                continue
            except NoKeyFoundError:
                other_entries.append(entry)
                continue

            entries = entrymap.setdefault(key, [])
            entries.append(entry)

        log.debug("Found valid entries: %s" % entrymap)
        log.debug("Found other entries: %s" % other_entries)

        return (entrymap, other_entries)

    def _remove_entry(self, entry):
        if self._use_bls:
            os.unlink(entry.bls_conf_path())
        else:
            grubby("--remove-kernel", entry.kernel)

    def _install_grubenv_efi(self):
        grubenv = "/boot/grub2/grubenv"
        efigrubenv = os.path.dirname(grub_cfg_path()) + "/grubenv"
        if os.path.isfile(grubenv) and not os.path.isfile(efigrubenv):
            log.debug("Copying %s to %s", grubenv, efigrubenv)
            shutil.copy2(grubenv, efigrubenv)
            os.unlink(grubenv)
            lnk = os.path.relpath(efigrubenv, os.path.dirname(grubenv))
            os.symlink(lnk, grubenv)
            try:
                os.unlink(grubenv + ".rpmnew")
            except Exception:
                pass

    def _update_grubenv(self, entry):
        if os.path.isdir("/sys/firmware/efi"):
            self._install_grubenv_efi()
        grub2_editenv("set", "saved_entry=%s" % entry.title)

    def add_entry(self, key, title, linux, initramfs, append):
        assert " " not in key
        log.debug("Adding entry: %s" % key)
        keyarg = " %s=%s" % (self._keyarg, key)
        append += keyarg

        kver = "-".join(os.path.basename(linux).rsplit("-")[-2:])
        if "(" not in title:
            title += " (%s)" % kver

        args = ["--copy-default",
                "--add-kernel", "/boot/%s" % linux,
                "--initrd", "/boot/%s" % initramfs,
                "--args", append,
                "--title", title]

        if self._use_bls:
            tmpdir = tempfile.mkdtemp()
            args += ["--bls-directory", tmpdir]

        grubby(*args)

        # Modify bls entry as grubby removes all the leading paths for the
        # kernel and initrd.  This is a workaround until
        # https://github.com/rhboot/grubby/pull/47 gets merged
        if self._use_bls:
            fname = glob.glob(tmpdir + "/*.conf")[0]
            f = File(fname)
            f.sub("\nlinux.*\n", "\nlinux /%s\n" % linux)
            f.sub("\ninitrd.*\n", "\ninitrd /%s\n" % initramfs)
            blsfname = "/boot/loader/entries/%s-%s.conf" % (key, kver)
            shutil.copy2(fname, blsfname)
            shutil.rmtree(tmpdir)

        return key

    def remove_entry(self, key):
        entries = self._get_valid_entries()
        key_entries = entries.pop(key, None)
        if not entries:
            log.debug("Not removing %s, no other entries found!", key)
            return
        if key_entries:
            for ke in key_entries:
                log.info("Removing boot entry: %s" % ke.title)
                self._remove_entry(ke)

    def set_default(self, key, update_grubenv=True):
        boot_entries = self._get_valid_entries()[key]
        entry = sorted(boot_entries, key=operator.attrgetter('title'),
                       reverse=True)[0]
        log.debug("Making default: %s" % entry.title)
        grubby("--set-default-index", entry.index)
        if update_grubenv:
            self._update_grubenv(entry)

    def get_default(self):
        log.debug("Getting default")
        kernel = grubby("--default-kernel")
        entries = self._get_valid_entries()
        try:
            entry = [b for e in entries for b in entries[e]
                     if b.kernel == kernel][0].title
        except IndexError:
            # Installing new kernels means we miss this. Check the others
            entry = [e for e in self._get_other_entries()
                     if e.kernel == kernel][0].title
        log.debug("Default: %s" % entry)
        return entry

    def list(self):
        return self._get_valid_entries()

    def list_other(self):
        return self._get_other_entries()

    def remove_other_entries(self):
        log.info("Removing other boot entries")
        entries = self._get_other_entries()
        for e in entries:
            log.debug("Removing other boot entry: %s" % e.title)
            self._remove_entry(e)

    def make_config(self):
        # UUID for /boot is set during build and never gets updated when using
        # BLS - this is bad, so we need to adjust our grub.cfg
        if not self._use_bls:
            return
        log.debug("BLS enabled, regenerating grub config file")
        # Ensure os-prober of the calling layer is disabled, otherwise we get
        # a bunch of irrelevant boot entries
        defgrub = ShellVarFile("/etc/default/grub")
        defgrub.set("GRUB_DISABLE_OS_PROBER", "true", force=True)
        grub2_mkconfig()


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

    @staticmethod
    def kernel_version(kernel):
        return "-".join(os.path.basename(kernel).rsplit("-")[-2:])

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

    def make_config(self):
        return self.bootloader.make_config()

    @staticmethod
    def validate():
        bytes_in_1G = 1000**3
        dirs = [d for d in find_mount_target() if "boot" in d]
        boot_dir = dirs[0] if dirs else None
        if boot_dir is None:
            raise RuntimeError("findmnt: error, unable to find boot partition"
                               " in target!")
        st = os.statvfs(boot_dir)
        bytes_in_boot_partition = st.f_blocks * st.f_frsize
        if bytes_in_boot_partition < bytes_in_1G:
            # 1G is 1073741824 bytes. However, if users use size=1000
            # in anaconda kickstart won't work. Based on that, let's
            # inform to users it's required 1.1G (size=1100).
            log.error("New /boot must have at least 1.1G size")
            raise BootPartitionRequires1G


# vim: sw=4 et sts=4:

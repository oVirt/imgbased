#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# imgbase
#
# Copyright (C) 2016  Red Hat, Inc.
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

from imgbased.bootloader import Grubby


FAKE_STDOUT = """index=0
kernel=/boot/ovirt-node-4.0+1/vmlinuz-3.10.0-327.4.5.el7.x86_64
args="ro crashkernel=auto rd.lvm.lv=centos_installed/root \
rd.lvm.lv=centos_installed/swap rhgb quiet LANG=en_US.UTF-8" img.bootid=a
root=/dev/mapper/centos_installed-root
initrd=/boot/ovirt-node-4.0+1/initramfs-3.10.0-327.4.5.el7.x86_64.img
title=ovirt-node-4.0+1
index=1
kernel=/boot/ovirt-node-4.0+1/vmlinuz-3.10.0-327.4.5.el7.x86_64
args="ro crashkernel=auto rd.lvm.lv=centos_installed/root \
rd.lvm.lv=centos_installed/swap rhgb quiet LANG=en_US.UTF-8" img.bootid=b
root=/dev/mapper/centos_installed-root
initrd=/boot/ovirt-node-4.0+1/initramfs-3.10.0-327.4.5.el7.x86_64.img
title=ovirt-node-4.0+1
"""


def _fake_grubby(*a, **kw):
    _fake_grubby.last_data = (a, kw)
    return FAKE_STDOUT


def test_simple_flow(mocker):
    """Tests the simple flow of the grubby bootloader."""
    mocker.patch("imgbased.bootloader.grubby", _fake_grubby)
    loader = Grubby(use_bls=False)

    r = loader.add_entry("a", "a-title", "vmlinuz-1.2-3", "a-initramfs",
                         "a-append")
    assert r == "a"
    assert _fake_grubby.last_data == (('--copy-default', '--add-kernel',
                                       '/boot/vmlinuz-1.2-3', '--initrd',
                                       '/boot/a-initramfs', '--args',
                                       'a-append img.bootid=a', '--title',
                                       'a-title (1.2-3)'),
                                      {})

    r = loader.remove_entry("a")
    assert _fake_grubby.last_data == (
        ('--remove-kernel',
         '/boot/ovirt-node-4.0+1/vmlinuz-3.10.0-327'
         '.4.5.el7.x86_64'),
        {}
    )

    r = loader.set_default("a", update_grubenv=False)
    assert _fake_grubby.last_data == (('--set-default-index', '0'), {})

# vim: sw=4 et sts=4:

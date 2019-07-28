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
# Author(s): Ryan Barry <rbarry@redhat.com>
#

import glob
import logging
import os
import socket
import subprocess
import uuid

from .. import constants, utils

log = logging.getLogger(__package__)


class RpmPersistenceError(Exception):
    pass


def pre_init(app):
    app.imgbase.hooks.create("rpms-persisted",
                             ("previous-lv_fullname", "new-lv_fullname"))


def init(app):
    app.imgbase.hooks.connect("os-upgraded", on_os_upgraded)


def on_os_upgraded(imgbase, previous_lv_name, new_lv_name):
    log.debug("Got: %s and %s" % (new_lv_name, previous_lv_name))

    # FIXME this can be improved by providing a better methods in .naming
    new_layer = imgbase.image_from_lvm_name(new_lv_name)
    new_lv = imgbase.lv_from_layer(new_layer)
    previous_layer_lv = \
        imgbase._lvm_from_layer(imgbase.naming.layer_before(new_layer))
    try:
        reinstall_rpms(imgbase, new_lv, previous_layer_lv)
    except Exception:
        log.exception("Failed to reinstall persisted RPMs")
        raise RpmPersistenceError()


def reinstall_rpms(imgbase, new_lv, previous_lv):
    if imgbase.mode == constants.IMGBASED_MODE_UPDATE:
        with utils.mounted(new_lv.path) as new_fs:
            new_etc = new_fs.path("/etc")
            new_rel = utils.SystemRelease(new_etc + "/system-release-cpe")

            if not new_rel.is_supported_product():
                log.error("Unsupported product: %s" % new_rel)
                raise RpmPersistenceError()

            with utils.bindmounted("/var", new_fs.path("/var"), rbind=True):
                install_rpms(new_fs)

        imgbase.hooks.emit("rpms-persisted", previous_lv.lv_name,
                           new_lv.lvm_name)
    else:
        log.info("Not reinstalling RPMs during system installation")


def install_rpms(new_fs):
    # Using `yum -y install` on the persisted rpms to avoid rewriting the logic
    # that yum uses when installing "installyonlypkgs" like kernel etc.
    # Using --noplugins will disable versionlocking or re-persisting the rpms
    def install(args):
        cmd = ["systemd-nspawn",
               "--uuid", str(uuid.uuid4()).replace("-", ""),
               "--machine", socket.getfqdn(),
               "-D", new_fs.path("/")] + args
        log.debug("Running %s" % cmd)
        try:
            subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            log.info("Failed to reinstall persisted RPMs!")
            log.info("Result: " + e.output)

    rpms = glob.glob("/var/imgbased/persisted-rpms/*.rpm")
    if rpms:
        machine_id = new_fs.path("/etc") + "/machine-id"
        backup = machine_id + ".bak"
        os.rename(machine_id, backup)
        with utils.SELinuxDomain("systemd_machined_t"):
            install(["yum", "install", "-y", "--noplugins"] + rpms)
        os.rename(backup, machine_id)

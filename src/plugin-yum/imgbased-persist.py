# -*- coding: utf-8 -*-
#
# Copy RPM packages to a lookaside folder on install
# Remove them from the lookaside path when removed
#
# Copyright © 2016 Red Hat, Inc.
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
# Author(s): Ryan Barry <rbarry@redhat.com>
#


import logging
import os
import shutil

from imgbased.bootsetup import BootSetupHandler
from yum.plugins import TYPE_CORE, TYPE_INTERACTIVE

requires_api_version = '2.3'
plugin_type = (TYPE_CORE, TYPE_INTERACTIVE)

persist_path = '/var/imgbased/persisted-rpms/'

# Annoying here as well, but this isn't available through any exposed
# properties/methods
yumlogger = logging.getLogger("yum.filelogging")
yumlogger.setLevel(logging.INFO)


def check_excluded(conduit, pkg):
    excluded_pkgs = conduit.confString("main", "excluded_pkgs").split(',')
    return pkg.po.name in excluded_pkgs


def check_bootsetup(conduit, pkg):
    bootsetup_pkgs = conduit.confString("main", "bootsetup_pkgs").split(',')
    return pkg.po.name in bootsetup_pkgs


def pretrans_hook(conduit):
    ts = conduit.getTsInfo()
    if ts.installed:
        if not os.path.isdir(persist_path):
            os.makedirs(persist_path)
        for pkg in ts.installed + ts.depinstalled + ts.depupdated:
            if check_excluded(conduit, pkg):
                continue
            rpm = pkg.po.localPkg()
            yumlogger.info("Persisting: %s" % os.path.basename(rpm))
            shutil.copy2(rpm, persist_path + os.path.basename(rpm))


def posttrans_hook(conduit):
    ts = conduit.getTsInfo()
    if ts.removed:
        for pkg in ts.removed:
            rpm = pkg.po.nvra + ".rpm"
            try:
                yumlogger.info("Unpersisting: %s" % rpm)
                os.remove(persist_path + rpm)
            except Exception:
                # Has probably never been persisted before. Manual RPM install?
                pass
    if ts.installed:
        bootsetup = False
        for pkg in ts.installed:
            if check_bootsetup(conduit, pkg):
                bootsetup = True
        if bootsetup:
            yumlogger.info("Updating boot configuration")
            BootSetupHandler().setup()

#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# imgbase
#
# Copyright (C) 2017 Red Hat, Inc.
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

import logging
import os
import subprocess
import time

from ..utils import call, RpmPackageDb, SELinuxDomain, ThreadRunner,\
    thread_group_handler


log = logging.getLogger(__package__)


def init(app):
    app.hooks.connect("pre-arg-parse", add_argparse)
    app.hooks.connect("post-arg-parse", post_argparse)


def add_argparse(app, parser, subparsers):
    s = subparsers.add_parser("firstboot",
                              help="Actions to run on the first boot of a"
                                   "new layer")
    s.add_argument("--configure", action="store_true",
                   help="Configure vdsm and run selinux scripts")


def post_argparse(app, args):
    if args.command == "firstboot":
        if args.configure:
            with SELinuxDomain("unconfined_service_t"):
                threads = []
                threads.append(ThreadRunner(configure_selinux))
                thread_group_handler(threads)

                if os.path.exists("/.imgbased-firstboot"):
                    os.remove("/.imgbased-firstboot")


def configure_vdsm():
    log.info("Configuring vdsm...")
    # Sleep a little so we're not racing ntpd/chronyd
    time.sleep(2)
    try:
        call(["vdsm-tool", "-v", "configure", "--force"])
    except:
        log.debug("Couldn't configure vdsm!'")


def configure_selinux():
    # Just a really trivial method so we can thread the selinux calls
    # alongside vdsm
    log.info("Running RPM %post scripts for selinux...")
    run_rpm_selinux_post()
    log.info("Relabeling the filesystem...")
    relabel_selinux()


def relabel_selinux():
    ctx_files = ["/etc/selinux/targeted/contexts/files/file_contexts",
                 "/etc/selinux/targeted/contexts/files/file_contexts.homedirs",
                 "/etc/selinux/targeted/contexts/files/file_contexts.local"]

    dirs = ["/etc", "/var", "/usr/libexec", "/usr/bin", "/usr/sbin"]

    for fc in ctx_files:
        if os.path.exists(fc):
            call(["/usr/sbin/setfiles", "-v", fc] + dirs)
        else:
            log.debug("{} not found in new fs, skipping".format(fc))


def run_rpm_selinux_post():
    run_commands = []
    critical_commands = ["restorecon", "semodule", "semanage", "fixfiles",
                         "chcon"]

    def just_do(arg, **kwargs):
        DEVNULL = open(os.devnull, "w")
        log.debug("Running %s" % arg)

        # shell=True is bad! But we're executing RPM %post scripts
        # directly and imgbased can't learn every possible way bash
        # can be written in order to make it sane
        proc = subprocess.Popen(arg, stdout=subprocess.PIPE,
                                stderr=DEVNULL, shell=True,
                                **kwargs).communicate()
        return proc[0]

    def filter_selinux_commands(rpms):
        for pkg, v in rpms.items():
            if any([c for c in critical_commands if c in v]):
                log.debug("Found a critical command in %s", pkg)
                run_commands.append("bash -c '{}'".format(v))

    log.debug("Checking whether any %post scripts from the new image must "
              "be run")
    rpmdb = RpmPackageDb()

    postin = rpmdb.get_script_type('POSTIN')
    posttrans = rpmdb.get_script_type('POSTTRANS')

    filter_selinux_commands(postin)
    filter_selinux_commands(posttrans)

    for r in run_commands:
        just_do(r)

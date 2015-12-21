#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# imgbase
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
from . import CliApplication

log = logging.getLogger()


def add_log_handler(lvl, fmt):
    try:
        from systemd import journal
        h = journal.JournalHandler(SYSLOG_IDENTIFIER=config.PACKAGE_NAME)
    except:
        h = logging.StreamHandler()
    h.setLevel(lvl)
    h.setFormatter(logging.Formatter(fmt))
    log.addHandler(h)


if __name__ == '__main__':
    log.setLevel(logging.INFO)
    add_log_handler(logging.INFO, "[%(levelname)s] %(message)s")

    CliApplication()

# vim: et sts=4 sw=4:

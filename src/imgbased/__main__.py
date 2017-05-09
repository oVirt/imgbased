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
import sys
from . import CliApplication

log = logging.getLogger()


if __name__ == '__main__':
    lvl = logging.DEBUG if "--debug" in sys.argv else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(message)s"

    handlers = [logging.StreamHandler()]
    try:
        from systemd import journal
        import config
        h = journal.JournalHandler(SYSLOG_IDENTIFIER=config.PACKAGE_NAME)
        handlers.append(h)
    except:
        log.debug("Failed to add journal handler")

    for h in handlers:
        h.setLevel(lvl)
        h.setFormatter(logging.Formatter(fmt))
        log.addHandler(h)

    log.setLevel(lvl)

    CliApplication()

# vim: et sts=4 sw=4:

#!/usr/bin/python
# -*- coding: utf-8 -*-
#
#
#
# Copyright (C) 2017  Red Hat, Inc.
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
import re

from .utils import File

log = logging.getLogger(__package__)


class TimeserverError(Exception):
    pass


class NoKeyFoundError(TimeserverError):
    pass


class TimeserverConfiguration(File):
    """Low-level object to access the timekeeping configuration
    """

    def __init__(self, filename, dry=False):
        super(TimeserverConfiguration, self).__init__(filename)

        if dry is False:
            self._parse()

    def _parse(self):
        keys = {}
        keys["servers"] = []
        for line in self.lines():
            if not re.match(r'^\s*#.*?', line) and line.strip():
                line = re.sub(r'#.*?$', '', line)
                try:
                    k, v = re.split(r'\s', line, maxsplit=1)
                    if k == "server":
                        keys["servers"].append(v.strip())
                    else:
                        keys[k] = v.strip()
                except Exception:
                    k = line
                    keys[k] = True

        self.keys = keys
        return keys

    def _set(self, k, v):
        if not hasattr(self, 'keys'):
            self._parse()
        self.keys[k] = v

    def _get(self, k=None, get_all=False):
        if not hasattr(self, 'keys'):
            self._parse()

        if get_all:
            return self.keys
        else:
            assert k is not None
            return self.keys[k]

    def get_servers(self):
        return self._get("servers")

    def set_servers(self, servers):
        self._set("servers", servers)

    def list_options(self):
        return self._get()

    def get_option(self, k):
        return self._get(k)

    def set_option(self, key, value):
        log.debug("Adding ntp option: %s" % key)

        assert " " not in key

        if key == "servers":
            self.set_servers(value)

        self._set(key, value)

    def remove_option(self, key):
        if not hasattr(self, 'keys'):
            self._parse()

        del self.keys[key]

    @property
    def _configuration(self):
        contents = "# This file has been migrated or modified by imgbased\n\n"

        if not hasattr(self, 'keys'):
            self._parse()

        for k, v in self.keys.iteritems():
            if k == "servers":
                for server in self.keys["servers"]:
                    contents += "server {server}\n".format(server=server)

            else:
                if v is True:
                    contents += "{key}\n".format(key=k)
                else:
                    contents += "{key} {value}\n".format(key=k, value=v)

        return contents

    def write_configuration(self):
        self.write(self._configuration)


class Ntp(TimeserverConfiguration):
    """This class knows how to parse a subset of ntp.conf

    >>> config = '''
    ... # Information about this file, see the man pages
    ... driftfile /var/lib/ntp/drift
    ... restrict default kod nomodify notrap nopeer noquery
    ... #restrict 192.168.1.0 mask 255.255.255.0 nomodify notrap
    ... server 1.2.3.4  # added by /sbin/dhclient-script
    ... server 1.2.4.5  # added by /sbin/dhclient-script
    ... '''

    >>> ntp = Ntp(None, dry=True)
    >>> ntp.read = lambda: config
    >>> ntp.lines = lambda: config.splitlines()
    >>> _ = ntp._parse()
    >>> ntp.get_servers()
    ['1.2.3.4', '1.2.4.5']
    >>> ntp.get_option('driftfile')
    '/var/lib/ntp/drift'
    >>> ntp.set_servers(['1.2.3.6', '1.2.3.7'])
    >>> ntp.get_servers()
    ['1.2.3.6', '1.2.3.7']
    >>> print(ntp._configuration)
    # This file has been migrated or modified by imgbased
    <BLANKLINE>
    restrict default kod nomodify notrap nopeer noquery
    driftfile /var/lib/ntp/drift
    server 1.2.3.6
    server 1.2.3.7
    <BLANKLINE>
    """


class Chrony(TimeserverConfiguration):
    """This class knows how to parse a subset of ntp.conf

    >>> config = '''
    ... # Use public servers from the pool.ntp.org project.
    ... # Please consider joining the pool (http://www.pool.ntp.org/join.html).
    ... pool 2.fedora.pool.ntp.org iburst
    ... # Specify file containing keys for NTP authentication.
    ... #keyfile /etc/chrony.keys
    ... # Specify directory for log files.
    ... logdir /var/log/chrony
    ... '''

    >>> chrony = Chrony(None, dry=True)
    >>> chrony.read = lambda: config
    >>> chrony.lines = lambda: config.splitlines()
    >>> _ = chrony._parse()
    >>> chrony.get_option('pool')
    '2.fedora.pool.ntp.org iburst'
    >>> print(chrony._configuration)
    # This file has been migrated or modified by imgbased
    <BLANKLINE>
    logdir /var/log/chrony
    pool 2.fedora.pool.ntp.org iburst
    <BLANKLINE>
    """

    def from_ntp(self, ntp):
        whitelist = [
            'acquisitionport',
            'clientloglimit',
            'cmdport',
            'cmdratelimit',
            'combinelimit',
            'corrtimeratio',
            'dumpdir',
            'hwclockfile',
            'keyfile',
            'leapsecmode',
            'leapsectz',
            'local',
            'lock_all',
            'log',
            'logbanner',
            'logchange',
            'logdir',
            'manual',
            'maxclockerror',
            'maxdistance',
            'maxdrift',
            'maxjitter',
            'maxsamples',
            'maxslewrate',
            'maxupdateskew',
            'minsamples',
            'minsources',
            'noclientlog',
            'ntpsigndsocket',
            'port',
            'rate.',
            'ratelimit',
            'reselectdist',
            'rtcautotrim',
            'rtcdevice',
            'rtcfile',
            'rtconutc',
            'rtcsync',
            'sched_priority',
            'servers',
            'stratumweight',
            'user'
        ]

        old_keys = ntp.keys

        delete_keys = []

        for d in old_keys.keys():
            if d not in whitelist:
                delete_keys.append(d)

        for d in delete_keys:
            del old_keys[d]

        for k, v in old_keys.items():
            self.set_option(k, v)

        if "servers" in old_keys:
            self.set_servers

        self.write_configuration()

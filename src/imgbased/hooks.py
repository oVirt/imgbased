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
import os
import subprocess


log = logging.getLogger(__package__)


class Hooks(object):
    """A quite simple hook mechanism, with some enforcement

    Hoos are created with a context to pass around informations:

     >>> hooks = Hooks(context='the-ctx')

     Before hooks can be used, they need to be created.
     Just trying to connect to or emit then, results in an exception:

     >>> hooks.connect("on-foo", lambda x, y: (y, x))
     Traceback (most recent call last):
     AssertionError: Unknown hook: on-foo

     >>> hooks.emit("on-foo")
     Traceback (most recent call last):
     AssertionError: Unknown hook: on-foo

     To create a hook you need to provide a name, and an argument
     specification, to document what kind of data the callback will get.

     >>> hooks.create("on-foo", ("time", "place"))

     Once created, you can attach a callback to a hook:

     >>> def concat_and_print(ctx, a, b):
     ...     print((ctx, a, b))

     >>> hooks.connect("on-foo", concat_and_print)

     And can also emit them:
     >>> hooks.emit("on-foo", "today", "here")
     ('the-ctx', 'today', 'here')

    """

    p = None
    hooks = None
    _argspecs = None

    def __init__(self, context=None):
        self.context = context
        self.hooks = {}
        self._argspecs = {}

    def create(self, name, argspec=None):
        """Create a hook

        Arguments:
          name: Name of the hook to create
        """
        assert name not in self.hooks, "Hook already exists: %s" % name
        self.hooks[name] = set()
        self._argspecs[name] = argspec

    def connect(self, name, cb):
        """Connect a callback to a hook

        Arguments:
          name: Name of the hook to connect to
          cb: Callback to call
        """
        argspec = self._argspecs.get(name, None)

        assert name in self.hooks, "Unknown hook: %s" % name
        assert (cb.__code__.co_argcount - 1) == len(argspec), \
            "Args for '%s' do not match signature: %s" % (name, argspec)
        self.hooks[name].add(cb)

    def unconnect(self, name, cb):
        self.hooks[name].remove(cb)

    def emit(self, name, *args):
        """Trigger a specific hook

        Arguments:
          name: Name of the hook to trigger
          args: Additional args to pass to the callback
        """
        argspec = self._argspecs.get(name, None)
        assert name in self.hooks, "Unknown hook: %s" % name
        assert len(args) == len(argspec), "Number of arguments does not match"

        wildcard = self.hooks.get(None, set())
        specific = self.hooks.get(name, set())
        all_cbs = wildcard.union(specific)

        for cb in all_cbs:
            log.debug("Triggering: %s (%s, %s)" % (cb, self.context, args))
            cb(self.context, *args)

    def add_filesystem_emitter(self, path):
        """Also call scripts on the fs if signals get emitted
        """
        def _trigger_fs(app, name, *args):
            """Trigger internal/pythonic hooks
            """
            if not os.path.exists(path):
                return
            for handler in os.listdir(path):
                script = os.path.join(path, handler)
                log.debug("Triggering: %s (%s %s)" % (script, name, args))
                subprocess.check_call([script, name] + list(args))
        self.create(None, _trigger_fs)

# vim: sw=4 et sts=4:

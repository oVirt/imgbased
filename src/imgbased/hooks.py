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


def log():
    return logging.getLogger("imgbase")


class Hooks(object):
    """A quite simple hook mechanism, with some enforcement

     >>> hooks = Hooks(None)

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

     >>> def concat_and_print(a, b):
     ...     print(a, b)

     >>> hooks.connect("on-foo", concat_and_print)

     And can also emit them:
     >>> hooks.emit("on-foo", "today", "here")
     ('today', 'here')

    """

    p = None
    hooksdir = "/usr/lib/imgbased/hooks.d/"
    hooks = None
    _argspecs = None

    def __init__(self, p):
        self.p = p
        self.hooks = {}
        self._argspecs = {}

        # A default wildcard hook is to also trigger
        # filesystem based hooks
        if p:
            self.hooks[None] = [self._trigger_fs]

    def create(self, name, argspec=None):
        """Create a hook

        Arguments:
          name: Name of the hook to create
        """
        self.hooks[name] = []
        self._argspecs[name] = argspec

    def connect(self, name, cb):
        """Connect a callback to a hook

        Arguments:
          name: Name of the hook to connect to
          cb: Callback to call
        """
        argspec = self._argspecs.get(name, None)

        assert name in self.hooks, "Unknown hook: %s" % name
        assert cb.func_code.co_argcount == len(argspec), \
            "Args for '%s' do not match signature: %s" % (name, argspec)
        self.hooks[name].append(cb)

    def emit(self, name, *args):
        """Trigger a specific hook

        Arguments:
          name: Name of the hook to trigger
          args: Additional args to pass to the callback
        """
        argspec = self._argspecs.get(name, None)
        assert name in self.hooks, "Unknown hook: %s" % name
        assert len(args) == len(argspec), "Number of arguments does not match"

        for cb in self.hooks.get(None, list()) + self.hooks.get(name, set()):
            log().debug("Triggering: %s (%s)" % (cb, args))
            cb(*args)

    def _trigger_fs(self, name, *args):
        """Trigger internal/pythonic hooks
        """
        if not os.path.exists(self.hooksdir):
            return
        for handler in os.listdir(self.hooksdir):
            script = os.path.join(self.hooksdir, handler)
            log().debug("Triggering: %s (%s %s)" % (script, name, args))
            self.p.run.call([script, name] + list(args))

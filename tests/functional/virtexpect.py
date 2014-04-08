#!/usr/bin/env python
"""
A simple class to do some kind of functional tests on VM images.
It works by redireting the console of a VM to stdio, which is then
handled with pexpect.
"""
import pexpect
import sys
import os
import logging


class Instance(object):
    log = None
    image = None
    qemu_cmd = "qemu-kvm -snapshot -hda %s \
        -m 1024 -serial stdio -net user -net nic"

    child = None

    def __init__(self):
        self.image = os.environ["VIRTEXPECT_IMAGE"]
        self.log = logging.getLogger(__name__)

    def spawn(self):
        child = pexpect.spawn(self.qemu_cmd % self.image)
        child.logfile = sys.stdout
        return child


class NodeInstance(Instance):
    """Makes more assumptions
    """

    def __enter__(self):
        self.child = self.spawn()
        return self

    def __exit__(self, *args, **kwargs):
        if self.child.isalive():
            self.child.sendline('init 0')
            self.child.close()

        if self.child.isalive():
            self.log.warn('Child did not exit gracefully.')
        else:
            self.log.debug('Child exited gracefully.')

    def login(self, username="root", password="r"):
        self.child.expect('(?i)login:')
        self.child.sendline('root')
        self.child.expect('(?i)password:')
        self.child.sendline('r')
        self.child.expect('# ')

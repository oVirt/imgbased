#!/usr/bin/env python
"""
A simple class to do some kind of functional tests on VM images.
It works by redireting the console of a VM to stdio, which is then
handled with pexpect.
"""
import pexpect
import sys
import logging


class Instance(object):
    log = None
    image = None

    child = None

    def __init__(self, image):
        assert image
        self.image = image
        self.log = logging.getLogger(__name__)

    def spawn(self):
        child = pexpect.spawn(self.qemu_cmd(self.image))
        child.logfile = sys.stdout
        return child

    def qemu_cmd(self, image):
        cmd = "qemu-kvm"
        cmd += " -m 1024 -serial stdio -net user -net nic"
        cmd += " -snapshot -hda %s" % image
        cmd += " -watchdog-action poweroff"
        #cmd += " -virtfs fsdriver,id=bar01,path=%s,
        #mount_tag=hostos,security_model=none" % shared_path
        return cmd

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

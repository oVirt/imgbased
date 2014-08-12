#!/usr/bin/env python
"""
A simple class to do some kind of functional tests on VM images.
It works by redireting the console of a VM to stdio, which is then
handled with pexpect.
"""
import subprocess
import sys
import re
import os

class Instance(object):
    child = None
    mount_tag = "hostos"
    guestpath_to_host = "/mnt/%s" % mount_tag

    def __init__(self, image, shared_path):
        assert os.path.exists(image)
        assert os.path.exists(shared_path)

        cmd = ["qemu-kvm",
               "-snapshot",
               "-display", "none",
               "-m", "1024",
               "-serial", "stdio",
               "-net", "user", "-net", "nic",
               "-hda", image,
               "-watchdog-action", "poweroff",
               "-virtfs",
               "local,id=hostos,path=%s,mount_tag=%s,security_model=none" % 
               (shared_path, self.mount_tag),
               ]

        self.child = subprocess.Popen(cmd,
                                      stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE)

    def wait(self, pattern):
        while True:
            for src, dst in [(self.child.stdout, sys.stdout)]:
#                             (self.child.stderr, sys.stderr)]:
                line = src.readline()
                dst.write(line)
                src.flush()
                if pattern and re.search(pattern, line):
                    return

    def tail(self):
        return self.wait(None)

    def sendline(self, line):
        print "sending: " + line
        self.child.stdin.write(line + "\n")

    def mount_hostos(self):
        cmd = "mkdir %s && " % self.guestpath_to_host
        cmd += "mount -t 9p -o trans=virtio %s %s" % (self.mount_tag,
                                                      self.guestpath_to_host)
        cmd += " && cd %s" % self.guestpath_to_host

        self.wait("~]#")
        self.sendline(cmd)


if __name__ == "__main__":
    image, shared_path, command = sys.argv[1:4]
    shell = Instance(image, shared_path)
    shell.mount_hostos()
    shell.sendline(command)
    shell.wait("Power down")


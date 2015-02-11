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

        cmd = ["qemu-system-x86_64",
               "-enable-kvm",
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
        """We need to read bytewise, because prompts are nto ended with a \n
        """
        line = ""
        while True:
            for src, dst in [(self.child.stdout, sys.stdout)]:
                #             (self.child.stderr, sys.stderr)]:
                char = src.read(1)
                line += char
                dst.write(char)
                src.flush()
                if pattern and re.search(pattern, line):
                    return
                if char == "\n":
                    line = ""

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

        self.sendline(cmd)


if __name__ == "__main__":
    image, shared_path, command = sys.argv[1:4]
    shell = Instance(image, shared_path)
    shell.wait("~]#")
    shell.mount_hostos()
    shell.sendline(command)
    shell.wait("Power down")

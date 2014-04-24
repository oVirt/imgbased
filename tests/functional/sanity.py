
import os
import tempfile
import unittest

from virtexpect import NodeInstance

IMAGE = os.environ.get("VIRTEXPECT_IMAGE", None)


class NodeTestCase(unittest.TestCase):
    node = None

    def setUp(self):
        shared_path = tempfile.mkdtemp(suffix="virtpexp")
        self.node = NodeInstance(IMAGE, shared_path)
        self.node.spawn()

    def tearDown(self):
        if self.node:
            self.node.poweroff()

    def log(self, msg):
        return self.node.log.info(msg)

    def sendline(self, txt):
        return self.node.child.sendline(txt)

    def expect(self, patterns, *args, **kwargs):
        return self.node.child.expect(patterns, *args, **kwargs)


class TestSanity(NodeTestCase):
    """Do some sanity testing on the image
    """
    def test_boot(self):
        self.log("Waiting for grub prompt")
        self.expect("Fedora, with Linux")

        self.log("Waiting for kernel output")
        self.expect("Booting")

        self.node.login()

    def test_9p(self):
        self.node.login()
        self.node.mount_hostos()

        self.log("Creating file on the host side")
        hostfile = self.node.shared_path + "/bar"
        os.system("echo echo Hi > %s" % hostfile)
        os.system("chmod a+x %s" % hostfile)

        self.log("Checking file on the guest side")
        self.node.enter_shared_path()
        self.sendline("./bar")
        self.expect("Hi")

        os.system("rm -f %s" % hostfile)


class TestImgbase(NodeTestCase):
    """Do sanity testing of the imgbase tool
    """
    def test_imgbase(self):
        self.node.login()

        self.sendline('lvs')
        self.expect('# ')
        self.sendline('lvs HostVG/Layer-0.0')
        self.expect('Layer-0.0', timeout=5)
        self.expect('# ')
        self.sendline('imgbase layer --add')
        self.expect('Adding a new layer')
        self.expect('Updating fstab')
        self.expect('# ')
        self.sendline('lvs HostVG/Layer-0.1')
        self.expect('Layer-0.1', timeout=5)


if __name__ == '__main__':
    unittest.main()

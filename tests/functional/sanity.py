
import os
import unittest

from virtexpect import NodeInstance

IMAGE = os.environ["VIRTEXPECT_IMAGE"]


class TestSanity(unittest.TestCase):
    """Do some sanity testing on the image
    """
    def test_boot(self):
        with NodeInstance(IMAGE) as node:
            node.login()


class TestImgbase(unittest.TestCase):
    """Do sanity testing of the imgbase tool
    """
    def test_imgbase(self):
        with NodeInstance(IMAGE) as node:
            child = node.child
            node.login()

            child.sendline('lvs')
            child.expect('# ')
            child.sendline('lvs HostVG/Layer-0.0')
            child.expect('Layer-0.0', timeout=5)
            child.expect('# ')
            child.sendline('imgbase layer --add')
            child.expect('Adding a new layer')
            child.expect('Updating fstab')
            child.expect('# ')
            child.sendline('lvs HostVG/Layer-0.1')
            child.expect('Layer-0.1', timeout=5)


if __name__ == '__main__':
    unittest.main()

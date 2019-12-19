import logging
import os
import os.path
import re
import uuid
from glob import glob

from .. import command, constants
from ..bootloader import BootConfiguration
from ..imgbase import ImageLayers
from ..utils import File, get_boot_args, safe_copy_file

log = logging.getLogger(__package__)


def init(app):
    app.hooks.connect("pre-arg-parse", add_argparse)
    app.hooks.connect("post-arg-parse", post_argparse)


def add_argparse(app, parser, subparsers):
    s = subparsers.add_parser("service", help="Image layers service")
    s.add_argument("--start", action="store_true", help="Runs on startup")
    s.add_argument("--stop", action="store_true", help="Runs on shutdown")


def post_argparse(app, args):
    if args.command == "service":
        if args.start:
            Startup().run()
        elif args.stop:
            Shutdown().run()


class ServiceHandler(object):
    def __init__(self):
        self._layer = str(ImageLayers().current_layer())

    def _get_kernel(self):
        boot_img = get_boot_args().get("BOOT_IMAGE")
        if not boot_img:
            raise RuntimeError("Could not find running kernel")
        return os.path.normpath("/boot/" + re.sub("\\(.*\\)", "", boot_img))


class Startup(ServiceHandler):
    def run(self):
        self._relabel_dev()
        self._copy_files_to_boot()
        self._generate_iqn()
        self._setup_layer_files()

    def _generate_iqn(self):
        initiator = "/etc/iscsi/initiatorname.iscsi"
        if os.path.exists(initiator):
            return
        log.debug("Description=Generate a random iSCSI initiator IQN name")
        suuid = str(uuid.uuid4()).split("-")[-1]
        factory_f = File("/usr/share/factory/etc/iscsi/initiatorname.iscsi")
        iqn = factory_f.contents.split(":")[0] + ":" + suuid + "\n"
        File(initiator).write(iqn)

    def _copy_files_to_boot(self):
        log.debug("Copying boot files to /boot")
        kernel = self._get_kernel()
        log.debug("Using kernel %s", kernel)
        dirname = os.path.dirname(kernel)
        kver = BootConfiguration.kernel_version(kernel)
        safe_copy_file(kernel, "/boot")
        for initrd in glob(dirname + "/init*%s*" % kver):
            safe_copy_file(initrd, "/boot")
        for dentry in ("/boot", dirname):
            [os.unlink(f) for f in
             glob("%s/%s.*" % (dentry, constants.IMGBASED_TMPFILE_PREFIX))]

    def _relabel_dev(self):
        log.debug("Relabeling /dev")
        command.call(["restorecon", "-rv", "/dev"])

    def _setup_layer_files(self):
        log.debug("Setting up files to layer %s", self._layer)


class Shutdown(ServiceHandler):
    def run(self):
        self._copy_files_from_boot()

    def _copy_files_from_boot(self):
        kernel = self._get_kernel()
        log.debug("Using kernel %s", kernel)
        kver = BootConfiguration.kernel_version(kernel)
        dirname, basename = os.path.split(kernel)
        log.debug("Copying files from /boot to %s", dirname)
        safe_copy_file("/boot/" + basename, dirname)
        # Copy the initrd for the running kernel version only
        for initrd in glob(dirname + "/init*%s*" % kver):
            safe_copy_file("/boot/" + os.path.basename(initrd), dirname)

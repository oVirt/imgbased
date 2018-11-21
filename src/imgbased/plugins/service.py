import os
import re
import uuid
import shutil
import os.path
import logging
import tempfile
from glob import glob
from ..bootloader import BootConfiguration
from ..utils import File, call
from ..imgbase import ImageLayers


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
    _tmp_prefix = "tmp.imgbase."

    def __init__(self):
        self._boot = BootConfiguration()
        self._layer = str(ImageLayers().current_layer())

    def _get_kernel(self):
        cmdline = File("/proc/cmdline").contents
        return "/boot" + [x.split("=")[1] for x in cmdline.split()
                          if x.startswith("BOOT_IMAGE=")][0]

    def _safe_copy_file(self, src, dst):
        dname = os.path.dirname(dst)
        fname = dst
        if os.path.isdir(dst):
            dname = dst
            fname = dst + "/" + os.path.basename(src)
        tmp = tempfile.mktemp(dir=dname, prefix=self._tmp_prefix)
        log.debug("Copy %s to %s", src, tmp)
        shutil.copy2(src, tmp)
        log.debug("Rename %s to %s", tmp, fname)
        os.rename(tmp, fname)


class Startup(ServiceHandler):
    def run(self):
        self._config_vdsm()
        self._clean_grub()
        self._relabel_dev()
        self._copy_files_to_boot()
        self._generate_iqn()
        self._setup_layer_files()

    def _config_vdsm(self):
        reconf_path = "/var/lib/ngn-vdsm-need-configure"
        if not os.path.exists(reconf_path):
            return
        log.debug("Reconfigure vdsm")
        call(["vdsm-tool", "-v", "configure", "--force"])
        os.unlink(reconf_path)

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
        self._safe_copy_file(kernel, "/boot")
        [self._safe_copy_file(x, "/boot") for x in glob(dirname + "/init*")]
        [os.unlink(x) for x in glob("%s/%s.*" % (dirname, self._tmp_prefix))]

    def _clean_grub(self):
        log.debug("Remove non-imgbased entries from grub")
        self._boot.remove_other_entries()

    def _relabel_dev(self):
        log.debug("Relabeling /dev")
        call(["restorecon", "-rv", "/dev"])

    def _setup_layer_files(self):
        log.debug("Setting up files to layer %s", self._layer)


class Shutdown(ServiceHandler):
    def run(self):
        self._fix_new_kernel()
        self._copy_files_from_boot()

    def _copy_files_from_boot(self):
        kernel = self._get_kernel()
        dirname, basename = os.path.split(kernel)
        log.debug("Copying files from /boot to %s", dirname)
        self._safe_copy_file("/boot/" + basename, dirname)
        initrds = [os.path.basename(x) for x in glob(dirname + "/init*")]
        [self._safe_copy_file("/boot/" + x, dirname) for x in initrds]

    def _fix_new_kernel(self):
        new_kernel_installed, new_version = self._check_new_kernel()
        if new_kernel_installed:
            self._fix_new_kernel_boot(new_version)

    def _check_new_kernel(self):
        # Compare the current kernel to the one from the factory
        current_kernel = call(["rpm", "-q", "kernel"]).strip()
        stock_kernel = call(["rpm", "-q", "--dbpath",
                             "/usr/share/factory/var/lib/rpm",
                             "kernel"]).strip()
        current_kernel = re.sub(r'^kernel-', '', current_kernel)
        stock_kernel = re.sub(r'^kernel-', '', stock_kernel)
        # Also make sure that the users have not reverted the
        # changes from new-kernel-pkg
        dflt_kernel = self._boot.get_default()
        if current_kernel != stock_kernel and current_kernel in dflt_kernel:
            return (True, current_kernel)
        return (False, current_kernel)

    def _fix_new_kernel_boot(self, new_kernel_version):
        # new-kernel-pkg erases our kernels from /boot
        # put them back for now so virt-v2v and friends still work
        old_kernels = glob("/boot/{}/vmlinuz*".format(self._layer))
        old_initrds = glob("/boot/{}/init*".format(self._layer))

        for kernel in old_kernels:
            log.info("Copying %s to %s" % (kernel, "/boot/"))
            self._safe_copy_file(kernel, "/boot")

        for initrd in old_initrds:
            log.info("Copying %s to %s" % (initrd, "/boot/"))
            self._safe_copy_file(initrd, "/boot")

        v, r = new_kernel_version.rsplit(".", 1)[0].rsplit("-", 2)[-2:]

        verrel = "{}-{}".format(v, r)

        new_kernel_files = glob("/boot/*{}*".format(verrel))

        for f in new_kernel_files:
            log.info("Copying %s to %s" % (f, "/boot/{}".format(self._layer)))
            self._safe_copy_file(f, "/boot/{}/".format(self._layer))

        if os.path.exists("/etc/grub2-efi.cfg"):
            call(["grub2-mkconfig", "-o", "/etc/grub2-efi.cfg"])
        else:
            call(["grub2-mkconfig", "-o", "/etc/grub2.cfg"])

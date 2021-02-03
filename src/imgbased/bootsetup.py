import logging
import os
import re

from . import utils
from .bootloader import BootConfiguration
from .command import chroot
from .lvm import LVM
from .naming import Layer

log = logging.getLogger(__package__)


class BootSetupHandler(object):
    def __init__(self, root="/", mkconfig=False, mkinitrd=False):
        self._root = root
        self._mkconfig = mkconfig
        self._mkinitrd = mkinitrd
        self._lv = LVM.LV.try_find(self._root)
        self._layer = Layer.from_lv_name(self._lv.lv_name)

    def _get_kernel_files(self):
        ret = {}
        pkgs = utils.RpmPackageDb()
        pkgs.dbpath = self._root + "/usr/share/rpm"
        kernels = pkgs.get_whatprovides("kernel")
        for krpm in kernels:
            kfiles = []
            for fname in pkgs.get_files([krpm]):
                if not fname.startswith("/boot"):
                    continue
                rfname = self._root + "/" + fname
                if os.path.exists(rfname):
                    kfiles.append(rfname)
                elif os.path.exists(fname):
                    kfiles.append(fname)
            if kfiles:
                ret[krpm] = kfiles
        log.debug("kfiles=%s", ret)
        if not ret:
            raise RuntimeError("kfiles were not found for %s" % kernels)
        return ret

    def _boot_path(self, kfiles, pattern):
        kfile = os.path.basename([x for x in kfiles if pattern in x][0])
        return os.path.normpath("/boot/{}/{}".format(self._lv.lv_name, kfile))

    def _run_dracut(self, initrd, kver):
        # This will create a new initrd in the new layer which will be copied
        # to the real /boot (under /boot/$layer) in _install_kernel
        log.debug("Regenerating initrd for %s", initrd)
        initrd_in_root = "/boot/" + os.path.basename(initrd)
        with utils.bindmounted("/proc", self._root + "/proc"):
            chroot(["dracut", "-f", "--add", "multipath",
                   initrd_in_root, kver], self._root)

    def _install_kernel(self, b, title, cmdline, kfiles):
        bootdir = "/boot/{}".format(self._lv.lv_name)
        if not os.path.isdir(bootdir):
            os.makedirs(bootdir)
        vmlinuz = self._boot_path(kfiles, "/vmlinuz")
        initrd = self._boot_path(kfiles, "/initramfs")
        if self._mkinitrd:
            self._run_dracut(initrd, BootConfiguration.kernel_version(vmlinuz))
        log.info("Copying kfiles for %s to %s...", title, bootdir)
        [utils.safe_copy_file(kf, bootdir) for kf in kfiles]
        [utils.safe_copy_file(kf, '/boot/') for kf in kfiles
            if re.search("vmlinuz", kf)]
        log.info("Adding bootloader entry %s (%s, %s)", title, vmlinuz, initrd)
        b.add(self._layer, title, vmlinuz.replace("/boot", ""),
              initrd.replace("/boot", ""), cmdline)

    def _get_cmdline(self):
        defgrub = utils.ShellVarFile("%s/etc/default/grub" % self._root)
        cmdline = defgrub.get("GRUB_CMDLINE_LINUX", "").strip('"').split()
        args = "rd.lvm.lv={0} root=/dev/{0}".format(self._lv.lvm_name).split()
        boot_uuid = utils.findmnt(["UUID"], path="/boot")
        if boot_uuid:
            args.append("boot=UUID={}".format(boot_uuid))
        args.append("rootflags=discard")
        for arg in args:
            if arg not in cmdline:
                cmdline.append(arg)
        return " ".join(cmdline)

    def _get_title(self):
        return utils.BuildMetadata(self._root).get("nvr")

    def setup(self):
        b = BootConfiguration()
        if self._mkconfig:
            b.make_config()
        cmdline = self._get_cmdline()
        title = self._get_title()
        installed = [os.path.normpath(y.kernel) for x in b.list().items()
                     for y in x[1]]
        for _, kfiles in sorted(self._get_kernel_files().items()):
            vmlinuz = self._boot_path(kfiles, "/vmlinuz")
            log.debug("Checking if %s is listed in %s", vmlinuz, installed)
            if vmlinuz not in installed:
                self._install_kernel(b, title, cmdline, kfiles)
            else:
                log.debug("No new kernel was detected")
        b.remove_other_entries()
        b.set_default(self._layer)

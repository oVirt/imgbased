
import glob
import json
import logging
import os
import shutil
import subprocess

from configparser import ConfigParser

from ..utils import BuildMetadata, File, Rsync, ShellVarFile, systemctl

log = logging.getLogger(__package__)


def init(app):
    app.hooks.connect("pre-arg-parse", add_argparse)
    app.hooks.connect("post-arg-parse", post_argparse)


def add_argparse(app, parser, subparsers):
    s = subparsers.add_parser("image-build",
                              help="Image build related tooling")
    s.add_argument("--postprocess", action="store_true",
                   help="Do some post-processing")
    s.add_argument("--set-nvr",
                   help="Define the nvr of this build")

    s = subparsers.add_parser("image-introspect",
                              help="Informations around this image")
    s.add_argument("--metadata",
                   action="store_true",
                   help="Print the metadata of this build (json)")


def post_argparse(app, args):
    if args.command == "image-build":
        if args.postprocess:
            Postprocessor.postprocess(app)
        if args.set_nvr:
            BuildMetadata().set("nvr", args.set_nvr)
    elif args.command == "image-introspect":
        if args.metadata:
            metadata = dict(BuildMetadata().items())
            print(json.dumps(metadata, indent=2))


def factorize(path):
    """Prepare a path for systemd's factory model

    Basically, keep the original build state in /usr/share/factory
    """
    fac = "/usr/share/factory/"

    if not os.path.isdir(fac):
        os.makedirs(fac)

    fpath = fac + path
    log.info("Factory: Copying {p} to {fp}".format(p=path, fp=fpath))
    rsync = Rsync()
    rsync.sync(path, fpath)


class Postprocessor():
    """
    >>> Postprocessor._steps = []
    >>> print(Postprocessor._steps)
    []

    >>> @Postprocessor.add_step
    ... def poo():
    ...     print("Poo")

    >>> Postprocessor.postprocess(None)
    Poo
    """
    _steps = []

    @classmethod
    def add_step(cls, func):
        cls._steps.append(func)

    @classmethod
    def postprocess(cls, app):
        log.info("Launching image post-processing")

        for func in cls._steps:
            func()

        # FIXME symlink in /etc: system-release, release-cpe, rpm


@Postprocessor.add_step
def factorize_paths():
    factorize("/etc")
    # FIXME Do we need ostree compat (-> /usr/etc)?
    factorize("/var")


@Postprocessor.add_step
def empty_machineid():
    """Empty the machine-id file, systemd will populate it
    """
    File("/etc/machine-id").truncate()


@Postprocessor.add_step
def relocate_rpm_and_yum_dbs():
    log.info("Relocating rpmdb")
    # Move out of /var
    shutil.move("/var/lib/rpm", "/usr/share/rpm")
    # Make 'rpm' look there
    with open('/etc/rpm/macros', 'w') as f:
        f.write('%_dbpath /usr/share/rpm\n')

    for d in ('yum', 'dnf'):
        orig_path = "/var/lib/{}".format(d)
        new_path = "/usr/share/{}".format(d)

        if not os.path.isdir(orig_path):
            log.info("%s does not exist, skipping", orig_path)
            continue

        log.info("Relocating and cleaning %s", orig_path)

        # Delete everything under yum
        shutil.rmtree(orig_path)

        # Then recreate it as a symlink
        os.mkdir(orig_path)
        shutil.move(orig_path, new_path)

        # Make the /var entry a symlink to the moved path
        os.symlink("../../" + new_path, orig_path)


@Postprocessor.add_step
def disable_and_clean_yum_repos():
    log.info("Conditionally disabling all yum repositories")
    repofiles = glob.glob("/etc/yum.repos.d/*")
    log.debug("Conditionally disabling repositories in files: %s" %
              repofiles)
    for fname in repofiles:
        val = "1" if "# imgbased: set-enabled" in File(fname).contents else "0"
        cp = ConfigParser(strict=False)
        cp.read(fname)
        for s in cp.sections():
            cp.set(s, "enabled", val)
        with open(fname, "w") as fobj:
            if val == "1":  # Keep the comment
                fobj.write("# imgbased: set-enabled\n")
            cp.write(fobj)
    log.info("Clean all yum data")
    subprocess.call(["dnf", "clean", "all", "--enablerepo=*"])


@Postprocessor.add_step
def check_etc_symlinks():
    log.info("Checking symlinks")

    def is_symlink(fn):
        log.debug("Checking if %s" % fn)
        if not os.path.islink(fn):
            raise RuntimeError("This file is not a symlink %s" % fn)

    fns = ["/etc/os-release"]

    # FIXME all relesae fiels should point to /usr/etc
    # fns += list(glob.glob("/etc/*release*")

    for fn in fns:
        is_symlink(fn)


@Postprocessor.add_step
def clean_ifcfgs_and_nmcons():
    log.info("Removing all ifcfg files and system connections, except lo")
    ifcfgs = glob.glob("/etc/sysconfig/network-scripts/ifcfg-*")
    nmcons = glob.glob("/etc/NetworkManager/system-connections/*")

    log.debug("ifcfgs: %s" % ifcfgs)
    log.debug("nmcons: %s" % nmcons)

    for fn in ifcfgs + nmcons:
        if fn.endswith("/ifcfg-lo"):
            continue
        else:
            log.debug("Removing %s" % fn)
            os.unlink(fn)


@Postprocessor.add_step
def clean_network_configs():
    """Remove files with network characteristics from the build. Anaconda
    will not overwrite them if they're present, and new ones will be written
    on the installed system
    """

    files = ["/etc/resolv.conf", "/etc/hostname"]
    for fn in files:
        if os.path.exists(fn):
            log.debug("Removing {0}".format(fn))
            os.unlink(fn)


@Postprocessor.add_step
def remove_iscsi_initiator_iqn():
    """Remove the iSCSI initiator IQN, to ensure that none is set
    A service is responsible for generating a new and uniqe name
    FIXME https://bugzilla.redhat.com/show_bug.cgi?id=1393833
    """
    fn = "/etc/iscsi/initiatorname.iscsi"
    if os.path.exists(fn):
        os.unlink(fn)


@Postprocessor.add_step
def systemctl_mask_lvmetad():
    osrel = ShellVarFile("/etc/os-release").parse()
    os_id, os_verid = osrel["ID"], osrel["VERSION_ID"]
    if os_id in ("centos", "rhel") and os_verid.startswith("7"):
        systemctl.mask("lvm2-lvmetad.service", "lvm2-lvmetad.socket")


@Postprocessor.add_step
def handle_bls_system():
    for entry in glob.glob("/boot/loader/entries/*"):
        os.unlink(entry)


# vim: sw=4 et sts=4

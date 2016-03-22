
import logging
import os
import shutil
import glob
import subprocess
from ..utils import Rsync, File, RpmPackageDb, BuildMetadata


log = logging.getLogger(__package__)


def init(app):
    app.hooks.connect("pre-arg-parse", add_argparse)
    app.hooks.connect("post-arg-parse", check_argparse)


def add_argparse(app, parser, subparsers):
    if not app.experimental:
        return

    s = subparsers.add_parser("image-build",
                              help="Image build related tooling")
    s.add_argument("--postprocess", action="store_true",
                   help="Do some post-processing")
    s.add_argument("--set-build-nvr-from-package",
                   help="Define which package defines the nvr of "
                   "this build")


def check_argparse(app, args):
    log.debug("Operating on: %s" % app.imgbase)
    if args.command == "image-build":
        if args.postprocess:
            Postprocessor.postprocess(app)
        if args.set_build_nvr_from_package:
            set_build_nvr_from_package(args.set_build_nvr_from_package)


def set_build_nvr_from_package(pkg):
    pkgdb = RpmPackageDb()
    nvr = pkgdb.get_nvr(pkg)
    BuildMetadata().set("nvr", nvr)


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
def handle_rpm_and_yum_dbs():
    log.info("Relocating rpmdb")
    # Move out of /var
    shutil.move("/var/lib/rpm", "/usr/share/rpm")
    # Make the /var entry a symlink to the moved db
    os.symlink("../../usr/share/rpm", "/var/lib/rpm")

    log.info("Cleaning yum")
    shutil.rmtree("/var/lib/yum")


@Postprocessor.add_step
def disable_and_clean_yum_repos():
    log.info("Disabling all yum repositories")
    repofiles = glob.glob("/etc/yum.repos.d/*")
    log.debug("Disabling repositories in files: %s" % repofiles)
    subprocess.call(["sed", "-i",
                     "/enabled=/ d ; /^\[/ a enabled=0"] + repofiles)
    subprocess.call(["yum", "clean", "all"])

# vim: sw=4 et sts=4


import logging
import os
import shutil
from ..utils import Rsync, File


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


def check_argparse(app, args):
    log.debug("Operating on: %s" % app.imgbase)
    if args.command == "image-build":
        if args.postprocess:
            postprocess(app)


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


def empty_machineid():
    """Empty the machine-id file, systemd will populate it
    """
    File("/etc/machine-id").truncate()


def handle_rpm_and_yum():
    log.info("Relocating rpmdb")
    # Move out of /var
    shutil.move("/var/lib/rpm", "/usr/share/rpm")
    # Make the /var entry a symlink to the moved db
    os.symlink("../../usr/share/rpm", "/var/lib/rpm")

    log.info("Cleaning yum")
    shutil.rmtree("/var/lib/yum")


def postprocess(app):
    log.info("Launching image post-processing")

    factorize("/etc")
    # FIXME Do we need ostree compat (-> /usr/etc)?
    factorize("/var")

    empty_machineid()

    handle_rpm_and_yum()

# vim: sw=4 et sts=4

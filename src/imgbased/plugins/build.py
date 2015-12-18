
import logging
import os
from ..utils import Rsync


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


def postprocess(app):
    log.info("Launching image post-processing")

    factorize("/etc")
    # ostree is using /usr/etc
    os.symlink("/usr/share/factory/etc", "/usr/etc")

    factorize("/var")

# vim: sw=4 et sts=4


import logging
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


def postprocess(app):
    log.info("Launching image post-processing")

    log.info("Copying /etc to /usr/etc")
    rsync = Rsync()
    rsync.sync("/etc", "/usr/etc")

# vim: sw=4 et sts=4

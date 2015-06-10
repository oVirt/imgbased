

import logging


log = logging.getLogger(__package__)


def init(app):
    app.hooks.connect("pre-arg-parse", add_argparse)
    app.hooks.connect("post-arg-parse", check_argparse)


def add_argparse(app, parser, subparsers):
    if not app.experimental:
        return

    s = subparsers.add_parser("kexec",
                              help="Boot into an image")
    s.add_argument("IMAGE", help="Image to use")


def check_argparse(app, args):
    log.debug("Operating on: %s" % app.imgbase)
    if args.command == "kexec":
        if args.image:
            raise NotImplemented()

# vim: sw=4 et sts=4

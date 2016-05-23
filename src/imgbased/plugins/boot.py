
import logging


log = logging.getLogger(__package__)


def init(app):
    app.hooks.connect("pre-arg-parse", add_argparse)
    app.hooks.connect("post-arg-parse", post_argparse)


def add_argparse(app, parser, subparsers):
    if not app.experimental:
        return

    s = subparsers.add_parser("boot",
                              help="Manage the bootloader")
    s.add_argument("--default",
                   help="Make this image the default boot entry")
    s.add_argument("IMAGE", help="Image to boot")


def post_argparse(app, args):
    if args.command == "boot":
        raise NotImplemented()

# vim: sw=4 et sts=4

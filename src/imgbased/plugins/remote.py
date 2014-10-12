
from ..utils import log


def init(app):
    app.hooks.connect("pre-arg-parse", add_argparse)
    app.hooks.connect("post-arg-parse", check_argparse)


def add_argparse(app, parser, subparsers):
    s = subparsers.add_parser("remote",
                              help="Fetch images from remote sources")
    s.add_argument("--nightly", action="store_true", help="Nightly image")
    s.add_argument("--stable", action="store_true", help="Stable image")

    # FIXME pull from jenkins based on config file


def check_argparse(app, args):
    log().debug("Operating on: %s" % app.imgbase)
    if args.command == "remote":
        raise NotImplemented()

# vim: sw=4 et sts=4

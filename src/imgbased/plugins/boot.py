
from ..utils import log

imgbase = None


def init(imgbase, hooks):
    imgbase = imgbase
    hooks.connect("pre-arg-parse", add_argparse)
    hooks.connect("post-arg-parse", check_argparse)


def add_argparse(parser, subparsers):
    s = subparsers.add_parser("boot",
                              help="Manage the bootloader")
    s.add_argument("--default",
                   help="Mkae this image the default boot entry")
    s.add_argument("IMAGE", help="Image to boot")


def check_argparse(args):
    if args.command == "boot":
        raise NotImplemented()

# vim: sw=4 et sts=4


import logging
from ..bootloader import BootConfiguration
from ..naming import Layer


log = logging.getLogger(__package__)


def init(app):
    app.hooks.connect("pre-arg-parse", add_argparse)
    app.hooks.connect("post-arg-parse", post_argparse)


def add_argparse(app, parser, subparsers):
    if not app.experimental:
        return

    s = subparsers.add_parser("boot",
                              help="Manage the bootloader")
    s.add_argument("--list", action="store_true",
                   help="List all entries")
    s.add_argument("--remove-other-boot-entries", action="store_true",
                   help="Remove non-layer entries from the bootloader")
    s.add_argument("--get-default", action="store_true",
                   help="Get the default layer")
    s.add_argument("--set-default", nargs=1, metavar="NVR",
                   help="Set the default layer")


def post_argparse(app, args):
    if args.command == "boot":
        boot = BootConfig()
        if args.list:
            print(boot.list())
        elif args.get_default:
            print(boot.get_default())
        elif args.set_default:
            layer = Layer.from_nvr(args.set_default)
            print(boot.set_default(layer))
        elif args.remove_other_boot_entries:
            boot.remove_other_entries()


class BootConfig():
    bootconfig = None

    def __init__(self):
        self.bootconfig = BootConfiguration()

    def list(self):
        return self.bootconfig.list()

    def get_default(self):
        return self.bootconfig.get_default()

    def set_default(self, nvr):
        layer = Layer.from_nvr(nvr)
        return self.bootconfig.set_default(layer)

    def remove_other_entries(self):
        return self.bootconfig.remove_other_entries()

# vim: sw=4 et sts=4


import logging
from .. import bootloader
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
        bootconfig = bootloader.BootConfiguration()
        if args.list:
            print(bootconfig.list())
        elif args.get_default:
            print(bootconfig.get_default())
        elif args.set_default:
            layer = Layer.from_nvr(args.set_default)
            print(bootconfig.set_default(layer))
        elif args.remove_other_boot_entries:
            bootconfig.remove_other_entries()

# vim: sw=4 et sts=4

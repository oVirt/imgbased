
import logging
from ..volume import Volumes


log = logging.getLogger(__package__)


def init(app):
    app.hooks.connect("pre-arg-parse", add_argparse)
    app.hooks.connect("post-arg-parse", post_argparse)


def add_argparse(app, parser, subparsers):
    if not app.experimental:
        return

    s = subparsers.add_parser("volume",
                              help="Volume management")
    s.add_argument("--list", action="store_true",
                   help="List all known volumnes")
    s.add_argument("--attach", metavar="PATH",
                   help="Attach a volume to the current layer")
    s.add_argument("--detach", metavar="PATH",
                   help="Detach a volume from the current layer")
    s.add_argument("--create", nargs=2, metavar=("PATH", "SIZE"),
                   help="Create a volume of SIZE for PATH")
    s.add_argument("--remove", metavar="PATH",
                   help="Remove the volume for PATH")


def post_argparse(app, args):
    if args.command == "volume":
        vols = Volumes(app.imgbase)
        if args.list:
            for v in vols.volumes():
                print(v)
        elif args.create:
            where, size = args.create
            vols.create(where, size)
        elif args.remove:
            vols.remove(args.remove)
        elif args.attach:
            vols.attach(args.attach)
        elif args.detach:
            vols.detach(args.detach)

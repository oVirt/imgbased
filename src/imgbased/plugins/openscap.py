import logging
from ..openscap import OSCAPScanner


log = logging.getLogger(__package__)


def init(app):
    app.hooks.connect("pre-arg-parse", add_argparse)
    app.hooks.connect("post-arg-parse", post_argparse)


def add_argparse(app, parser, subparsers):
    s = subparsers.add_parser("openscap", help="Security management")
    s.add_argument("--all", action="store_true",
                   help="List all available profiles")
    s.add_argument("--list", action="store_true",
                   help="List registered profile")
    s.add_argument("--configure", action="store_true",
                   help="Auto configure SCAP profile and datastream")
    s.add_argument("--register", nargs=2, metavar=("DATASTREAM", "PROFILE"),
                   help="Register data for scanning")
    s.add_argument("--unregister", metavar="PROFILE",
                   help="Register data for scanning")
    s.add_argument("--scan", metavar="PATH",
                   help="Use registered profile to perform a scan")
    s.add_argument("--remediate", metavar="PATH",
                   help="Use registered profile to remediate system")


def post_argparse(app, args):
    if args.command == "openscap":
        os = OSCAPScanner()
        if args.list:
            print("Registered profile: %s" % os.profile)
        elif args.all:
            for id_, desc in os.profiles().items():
                print("Id: %s\n    %s\n" % (id_, desc))
        elif args.configure:
            os.configure()
        elif args.register:
            datastream, profile = args.register
            os.register(datastream, profile)
        elif args.unregister:
            os.unregister(args.unregister)
        elif args.scan:
            os.scan(remediate=False, path=args.scan)
        elif args.remediate:
            os.scan(remediate=True, path=args.remediate)


imgbase = None


def init(imgbase, hooks):
    imgbase = imgbase
    hooks.connect("pre-arg-parse", add_argparse)
    hooks.connect("post-arg-parse", check_argparse)


def add_argparse(parser, subparsers):
    s = subparsers.add_parser("remote",
                              help="Fetch images from remote sources")
    s.add_argument("--nightly", action="store_true", help="Nightly image")
    s.add_argument("--stable", action="store_true", help="Stable image")

    # FIXME pull from jenkins based on config file


def check_argparse(args):
    pass


imgbase = None

def init(imgbase, hooks):
    imgbase = imgbase
    hooks.connect("on-arg-parse", add_argparse)


def add_argparse(parser, subparsers):
    s = subparsers.add_parser("update",
                              help="Update from upstream Jenkins")
    s.add_argument("--nightly", action="store_true", help="Nightly image")
    s.add_argument("--stable", action="store_true", help="Stable image")

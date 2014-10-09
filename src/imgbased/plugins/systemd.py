
imgbase = None

def init(imgbase, hooks):
    imgbase = imgbase
    hooks.connect("pre-arg-parse", add_argparse)


def add_argparse(parser, subparsers):
    s = subparsers.add_parser("nspawn",
                              help="Spawn a container with the image as a root")
    s.add_argument("IMAGE", help="Image to use")

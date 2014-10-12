
import difflib
import sys

from ..utils import mounted, log

imgbase = None


def init(imgbase, hooks):
    imgbase = imgbase
    hooks.connect("pre-arg-parse", add_argparse)
    hooks.connect("post-arg-parse", check_argparse)


def add_argparse(parser, subparsers):
    s = subparsers.add_parser("diff",
                              help="Compare layers and bases")
    s.add_argument("image", nargs=2,
                   help="Base/Layer to compare")


def check_argparse(args):
    if args.command == "diff":
        if len(args.image) == 2:
            sys.stdout.writelines(imgbase.diff(*args.image))


def diff(left, right, mode="tree"):
    """

    Args:
        left: Base or layer
        right: Base or layer
        mode: tree, content, unified
    """
    log().info("Diff '%s' between '%s' and '%s'" % (left, right, mode))

    imgl = imgbase.image_from_name(left)
    imgr = imgbase.image_from_name(right)

    with mounted(imgl.path) as mountl, \
            mounted(imgr.path) as mountr:
        if mode == "tree":
            l = imgbase.run.find(["-ls"], cwd=mountl.target).splitlines(True)
            r = imgbase.run.find(["-ls"], cwd=mountr.target).splitlines(True)
            udiff = difflib.unified_diff(r, l, fromfile=left, tofile=right,
                                         n=0)
            return (l for l in udiff if not l.startswith("@"))
        else:
            raise RuntimeError("Unknown diff mode: %s" % mode)

# vim: sw=4 et sts=4

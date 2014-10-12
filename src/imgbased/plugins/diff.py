
import difflib
import sys

from ..utils import mounted, log


def init(app):
    app.hooks.connect("pre-arg-parse", add_argparse)
    app.hooks.connect("post-arg-parse", check_argparse)


def add_argparse(app, parser, subparsers):
    s = subparsers.add_parser("diff",
                              help="Compare layers and bases")
    s.add_argument("image", nargs=2,
                   help="Base/Layer to compare")


def check_argparse(app, args):
    log().debug("Operating on: %s" % app.imgbase)
    if args.command == "diff":
        if len(args.image) == 2:
            sys.stdout.writelines(diff(app.imgbase, *args.image))


def diff(imgbase, left, right, mode="tree"):
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

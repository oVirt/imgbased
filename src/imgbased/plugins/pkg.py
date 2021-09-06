
import difflib
import sys
import logging

from ..utils import mounted, RpmPackageDb
from ..naming import Image


log = logging.getLogger(__package__)


def init(app):
    app.hooks.connect("pre-arg-parse", add_argparse)
    app.hooks.connect("post-arg-parse", post_argparse)


def add_argparse(app, parser, subparsers):
    if not app.experimental:
        return

    s = subparsers.add_parser("pkg",
                              help="Package related tooling")

    s.add_argument("--diff",
                   metavar="OTHER-IMAGE",
                   help="Run a package diff")

    s.add_argument("IMAGE",
                   help="Base/Layer to compare")


def post_argparse(app, args):
    if args.command == "pkg":
        if args.IMAGE and args.diff:
            sys.stdout.writelines(diff(app.imgbase, args.diff, args.IMAGE))
        else:
            log.warn("Two images are required for a diff")


def diff(imgbase, left, right, mode="default"):
    """

    Args:
        left: Base or layer
        right: Base or layer
        mode: tree, content, unified
    """
    log.info("Diff '%s' between '%s' and '%s'" % (mode, left, right))

    imgl = imgbase._lvm_from_layer(Image.from_nvr(left))
    imgr = imgbase._lvm_from_layer(Image.from_nvr(right))

    with mounted(imgl.path) as mountl, mounted(imgr.path) as mountr:
        if mode == "default":
            pkgdb = RpmPackageDb()
            pkgdb.root = mountl.target
            lside = sorted(pkgdb.get_packages())
            pkgdb.root = mountr.target
            rside = sorted(pkgdb.get_packages())
            udiff = difflib.unified_diff(lside, rside, fromfile=left,
                                         tofile=right, n=0, lineterm="")
            return (line + "\n" for line in udiff if not line.startswith("@"))
        else:
            raise RuntimeError("Unknown diff mode: %s" % mode)

# vim: sw=4 et sts=4

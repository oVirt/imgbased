
import difflib
import sys
import logging

from ..utils import mounted


log = logging.getLogger(__package__)


def init(app):
    app.hooks.connect("pre-arg-parse", add_argparse)
    app.hooks.connect("post-arg-parse", check_argparse)


def add_argparse(app, parser, subparsers):
    if not app.experimental:
        return

    s = subparsers.add_parser("pkg",
                              help="Package related tooling")

    s.add_argument("--diff",
                   help="Run a package diff")

    s.add_argument("image", nargs=2,
                   help="Base/Layer to compare")


def check_argparse(app, args):
    log.debug("Operating on: %s" % app.imgbase)
    if args.command == "pkg" and args.diff:
        if len(args.image) == 2:
            sys.stdout.writelines(diff(app.imgbase, *args.image))
        else:
            log.warn("Two images are required for a diff")


def diff(imgbase, left, right, mode="default"):
    """

    Args:
        left: Base or layer
        right: Base or layer
        mode: tree, content, unified
    """
    log.info("Diff '%s' between '%s' and '%s'" % (left, right, mode))

    imgl = imgbase.image_from_name(left)
    imgr = imgbase.image_from_name(right)

    with mounted(imgl.path) as mountl, \
            mounted(imgr.path) as mountr:
        if mode == "default":
            pkgdb = RpmPackageDb()
            pkgdb.root = mountl.target
            l = sorted(pkgdb.get_packages())
            pkgdb.root = mountr.target
            r = sorted(pkgdb.get_packages())
            udiff = difflib.unified_diff(l, r, fromfile=left, tofile=right,
                                         n=0)
            return (l + "\n" for l in udiff if not l.startswith("@"))
        else:
            raise RuntimeError("Unknown diff mode: %s" % mode)

# vim: sw=4 et sts=4

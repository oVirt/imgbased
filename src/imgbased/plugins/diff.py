
import difflib
import os
import sys
import logging

from ..utils import mounted, ExternalBinary


log = logging.getLogger(__package__)


def init(app):
    app.hooks.connect("pre-arg-parse", add_argparse)
    app.hooks.connect("post-arg-parse", check_argparse)


def add_argparse(app, parser, subparsers):
    if not app.experimental:
        return

    d = subparsers.add_parser("diff",
                              help="Compare layers and bases")
    d.add_argument("-m", "--mode",
                   help="Mode: tree, content",
                   default="tree")
    d.add_argument("image", nargs=2,
                   help="Base/Layer to compare")

    c = subparsers.add_parser("factory-diff",
                              help="Compare runtime to factory")
    c.add_argument("--config", help="Compare config")


def check_argparse(app, args):
    log.debug("Operating on: %s" % app.imgbase)
    if args.command == "diff":
        if len(args.image) == 2:
            diff(app.imgbase, *args.image, mode=args.mode)
    elif args.command == "factory-diff":
        if args.config:
            path_diff("/usr/etc", "/etc", "content")


def diff(imgbase, left, right, mode="tree"):
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
        return path_diff(mountl.target, mountr.target, mode)


def path_diff(left, right, mode):
    for p in [left, right]:
        if not os.path.exists(p):
            raise RuntimeError("Path does not exist: %r" % p)

    if mode == "tree":
        l = ExternalBinary().find(["-ls"], cwd=left).splitlines(True)
        r = ExternalBinary().find(["-ls"], cwd=right).splitlines(True)
        udiff = difflib.unified_diff(r, l, fromfile=left, tofile=right,
                                     n=0)
        lines = (l for l in udiff if not l.startswith("@"))
        sys.stdout.writelines(lines)
    elif mode == "content":
        import subprocess
        subprocess.call(["diff", "-urN",
                         left, right],
                        stderr=subprocess.DEVNULL)
    else:
        raise RuntimeError("Unknown diff mode: %s" % mode)

# vim: sw=4 et sts=4

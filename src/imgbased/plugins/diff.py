
import difflib
import os
import sys
import logging

from .. import utils


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
    d.add_argument("image", nargs="*",
                   help="Base/Layer to compare")

    c = subparsers.add_parser("factory-diff",
                              help="Compare runtime to factory")
    c.add_argument("--config", help="Compare config")


def check_argparse(app, args):
    log.debug("Operating on: %s" % app.imgbase)
    if args.command == "diff":
        imgs = None
        if len(args.image) == 0:
            curlay = app.imgbase.current_layer().nvr
            curbase = app.imgbase.base_of_layer(curlay).nvr
            imgs = [curbase, curlay]
        elif len(args.image) == 2:
            imgs = args.image
        else:
            raise RuntimeError("Please specify 0 or 2 images")
        diff(app.imgbase, *imgs, mode=args.mode)

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
    log.info("Diff '%s' between '%s' and '%s'" % (mode, left, right))

    imgl = imgbase.image_from_name(left)
    imgr = imgbase.image_from_name(right)

    with utils.mounted(imgl.path, target="/mnt/%s" % left) as mountl, \
            utils.mounted(imgr.path, target="/mnt/%s" % right) as mountr:
        return path_diff(mountl.target, mountr.target, mode,
                         left, right)


def path_diff(left, right, mode, left_alias=None, right_alias=None):
    left_alias = left_alias or left
    right_alias = right_alias or right

    for p in [left, right]:
        if not os.path.exists(p):
            raise RuntimeError("Path does not exist: %r" % p)

    if mode == "tree":
        l = utils.findls(left)
        r = utils.findls(right)
        udiff = difflib.unified_diff(r, l, fromfile=left_alias,
                                     tofile=right_alias, n=0)
        lines = (l for l in udiff if not l.startswith("@"))
        sys.stdout.writelines(lines)
    elif mode == "content":
        import subprocess
        subprocess.call(["diff", "-urN",
                         left, right])
    else:
        raise RuntimeError("Unknown diff mode: %s" % mode)

# vim: sw=4 et sts=4

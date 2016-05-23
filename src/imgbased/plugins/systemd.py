
import logging
from subprocess import check_call

from .. import utils
from ..naming import Image


log = logging.getLogger(__package__)


def init(app):
    app.hooks.connect("pre-arg-parse", add_argparse)
    app.hooks.connect("post-arg-parse", post_argparse)


def add_argparse(app, parser, subparsers):
    if not app.experimental:
        return

    s = subparsers.add_parser("nspawn",
                              help="Boot into an image")
    s.add_argument("IMAGE", help="Image to use")
    s.add_argument("NSPAWN_ARGS",
                   help="Arguments and command passed to nspawn",
                   nargs="*",
                   default="")


def post_argparse(app, args):
    if args.command == "nspawn":
        if args.IMAGE:
            systemd_nspawn(app.imgbase, args.IMAGE, args.NSPAWN_ARGS)


def systemd_nspawn(imgbase, layer, nspawn_args):
    """Spawn a container off the root of layer layer
    """
    log.info("Spawning the layer in a new namespace")

    img = imgbase._lvm_from_layer(Image.from_nvr(layer))

    with utils.mounted(img.path) as mnt:
        check_call(["systemd-nspawn",
                    "-D", mnt.target,
                    ] + nspawn_args)

# vim: sw=4 et sts=4

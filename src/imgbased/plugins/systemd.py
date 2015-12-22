
import logging

from .. import utils


log = logging.getLogger(__package__)


def init(app):
    app.hooks.connect("pre-arg-parse", add_argparse)
    app.hooks.connect("post-arg-parse", check_argparse)


def add_argparse(app, parser, subparsers):
    if not app.experimental:
        return

    s = subparsers.add_parser("nspawn",
                              help="Boot into an image")
    s.add_argument("IMAGE", help="Image to use")
    s.add_argument("COMMAND", help="Command to run inside the container",
                   nargs="?",
                   default="")


def check_argparse(app, args):
    log.debug("Operating on: %s" % app.imgbase)
    if args.command == "nspawn":
        if args.IMAGE:
            nspawn(app.imgbase, args.IMAGE, args.COMMAND)


def nspawn(imgbase, layer, cmd=""):
    """Spawn a container off the root of layer layer
    """
    log.info("Spawning the layer in a new namespace")

    img = imgbase.naming.image_from_name(layer)

    cmds = [cmd] if cmd else []
    mname = layer.replace(".", "-")
    with utils.mounted(img.lvm.path) as mnt:
        utils.nspawn("-n",
                     "-D", mnt.target,
                     "--machine", mname,
                     "--read-only",
                     *cmds)

# vim: sw=4 et sts=4

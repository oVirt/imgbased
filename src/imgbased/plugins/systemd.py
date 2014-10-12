
import subprocess

from ..utils import log

imgbase = None


def init(imgbase, hooks):
    imgbase = imgbase
    hooks.connect("pre-arg-parse", add_argparse)
    hooks.connect("post-arg-parse", check_argparse)


def add_argparse(parser, subparsers):
    s = subparsers.add_parser("nspawn",
                              help="Boot into an image")
    s.add_argument("IMAGE", help="Image to use")


def check_argparse(args):
    if args.command == "nspawn":
        if args.image:
            nspawn(args.image)


def nspawn(layer, cmd=""):
    """Spawn a container off the root of layer layer
    """
    log().info("Adding a boot entry for the new layer")

    img = imgbase.image_from_name(layer)

    cmds = [cmd] if cmd else []
    subprocess.call(["systemd-nspawn",
                     "--image", img.path,
                     "--machine", layer,
                     "--read-only"] + cmds)

# vim: sw=4 et sts=4

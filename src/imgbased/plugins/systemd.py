
import subprocess

from ..utils import log


def init(app):
    app.hooks.connect("pre-arg-parse", add_argparse)
    app.hooks.connect("post-arg-parse", check_argparse)


def add_argparse(app, parser, subparsers):
    s = subparsers.add_parser("nspawn",
                              help="Boot into an image")
    s.add_argument("IMAGE", help="Image to use")
    s.add_argument("COMMAND", help="Command to run inside the container",
                   nargs="?",
                   default="")


def check_argparse(app, args):
    log().debug("Operating on: %s" % app.imgbase)
    if args.command == "nspawn":
        if args.image:
            nspawn(app.imgbase, args.image, args.command)


def nspawn(imgbase, layer, cmd=""):
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

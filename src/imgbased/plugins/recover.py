import os
import six
import logging

from ..bootloader import BootConfiguration
from ..config import paths
from ..naming import NVR
from ..volume import Volumes


log = logging.getLogger(__package__)


def init(app):
    app.hooks.connect("pre-arg-parse", add_argparse)
    app.hooks.connect("post-arg-parse", post_argparse)


def add_argparse(app, parser, subparsers):
    if not app.experimental:
        return

    s = subparsers.add_parser("recover",
                              help="Recover from failed upgrades")
    s.add_argument("--force", action="store_true",
                   help="Override confirmations")
    s.add_argument("--list", action="store_true",
                   help="List unused LVs")


def post_argparse(app, args):
    if args.command == "recover":
        ImageRecovery(app.imgbase).process(lst=args.list, force=args.force)


class ImageRecovery:
    def __init__(self, imgbase):
        self._imgbase = imgbase
        self._volumes = Volumes(self._imgbase)

    def process(self, lst=False, force=False):
        log.debug("lst=%s, force=%s", lst, force)
        layers = self._get_unused_layers()
        volumes = self._get_unused_volumes()
        if lst:
            self._display_unused(layers, volumes)
            return
        self._remove_lvs(layers, volumes, force)

    def _get_unused_layers(self):
        boot_entries = [NVR.parse(b) for b in BootConfiguration().list()]
        layers = self._imgbase.naming.layers()
        return [l for l in layers if l.nvr not in boot_entries]

    def _get_unused_volumes(self):
        not_mounts = [p for p in sorted(paths) if not os.path.ismount(p)]
        return [p for p in not_mounts if self._volumes.is_volume(p)]

    def _prompt(self, what, name, force):
        if force:
            return True
        prompt = "Remove %s %s? [y/N]: " % (what, name)
        return six.moves.input(prompt).lower() == 'y'

    def _remove_lvs(self, layers, volumes, force):
        for vol in volumes:
            if self._prompt("volume on", vol, force):
                print("Removing volume on: [%s]" % vol)
                self._volumes.remove(vol, force=True)
        for layer in layers:
            if self._prompt("LV", layer, force):
                print("Removing LV base: [%s]" % layer.base.nvr)
                self._imgbase.remove_base(layer.base.nvr)

    def _display_unused(self, layers, volumes):
        if layers:
            print("Found the following unused layers:")
            for layer in layers:
                print(layer.nvr)
        else:
            print("No unused layers")
        if volumes:
            print("Found the following unused volumes:")
            for vol in volumes:
                print(vol)
        else:
            print("No unused volumes")

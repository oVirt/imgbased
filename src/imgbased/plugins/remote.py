
from ..utils import sorted_versions, request_url, mounted, \
    size_of_fstree
from ..local import Configuration
from six.moves import configparser
from io import StringIO
import argparse
import sys
import re
import os
import hashlib
import tempfile
import subprocess
import glob
import logging
try:
    from urllib.request import unquote
except ImportError:
    from urllib import unquote


log = logging.getLogger(__package__)


def init(app):
    app.hooks.connect("pre-arg-parse", add_argparse)
    app.hooks.connect("post-arg-parse", check_argparse)


def add_argparse(app, parser, subparsers):
    """Add our argparser bit's to the overall parser
    It will be called when the app is launched
    """
    s = subparsers.add_parser("liveimg",
                              help="Liveimg handling")

    su = s.add_subparsers(help="Commands around liveimg", dest="subcmd")

    su_add = su.add_parser("update",
                           help="Update from a liveimg")
    su_add.add_argument("VENDORID")
    su_add.add_argument("VERSION")
    su_add.add_argument("RELEASE")
    su_add.add_argument("FILENAME")


def check_argparse(app, args):
    """Check if we were asked to do something
    It will be called when the user selects a sub-command
    """
    log.debug("Operating on: %s" % app.imgbase)

    if args.command == "update":
        new_base = LiveimgExtractor(app.imgbase)\
            .extract(args.filename,
                     args.vendorid,
                     args.version,
                     args.release)
        assert new_base
        app.imgbase.add_layer(new_base)
        log.info("Update was pulled successfully")


class LiveimgExtractor():
    imgbase = None
    can_pipe = False

    def __init__(self, imgbase):
        self.imgbase = imgbase

    def _recommend_size_for_tree(self, path, scale=2.0):
        scaled = size_of_fstree(path) * scale
        remainder = scaled % 512
        return int(scaled + (512 - remainder))

    def write(self, image):
        raise NotImplementedError

    def extract(self, liveimgfile, vendorid, version, release):
        new_base = None
        log.info("Extracting image '%s'" % image)
        with mounted(liveimgfile) as squashfs:
            log.debug("Mounted squashfs")
            liveimg = glob.glob(squashfs.target + "/*/*.img").pop()
            log.debug("Found fsimage at '%s'" % liveimg)
            with mounted(liveimg) as rootfs:
                size = self._recommend_size_for_tree(rootfs.target, 3.0)
                log.debug("Recommeneded base size: %s" % size)
                log.info("Starting base creation")
                add_tree = self.imgbase.add_base_with_tree
                new_base = add_tree(rootfs.target,
                                    "%sB" % size,
                                    name=vendorid,
                                    version=version,
                                    release=release)
                log.info("Files extracted")
        log.debug("Extraction done")
        return new_base

# vim: sw=4 et sts=4:


import glob
import logging
import os
from ..utils import size_of_fstree, mounted, Ext4, Rsync

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

    def add_base_with_tree(self, sourcetree, size, name, version=None,
                           release=None, lvs=None):
        new_base_lv = self.imgbase.add_base(size, name,
                                            version, release, lvs)

        if not os.path.exists(sourcetree):
            raise RuntimeError("Sourcetree does not exist: %s" % sourcetree)

        with new_base_lv.unprotected():
            log.info("Creating new filesystem on base")
            if not self.dry:
                Ext4.mkfs(new_base_lv.path, self.debug)

            log.info("Writing tree to base")
            with mounted(new_base_lv.path) as mount:
                dst = mount.target + "/"
                rsync = Rsync()
                rsync.sync(sourcetree, dst)
                log.debug("Trying to copy prev fstab")

        return new_base_lv

    def extract(self, liveimgfile, vendorid, version, release):
        new_base = None
        log.info("Extracting image '%s'" % liveimgfile)
        with mounted(liveimgfile) as squashfs:
            log.debug("Mounted squashfs")
            liveimg = glob.glob(squashfs.target + "/*/*.img").pop()
            log.debug("Found fsimage at '%s'" % liveimg)
            with mounted(liveimg) as rootfs:
                size = self._recommend_size_for_tree(rootfs.target, 3.0)
                log.debug("Recommeneded base size: %s" % size)
                log.info("Starting base creation")
                add_tree = self.add_base_with_tree
                new_base = add_tree(rootfs.target,
                                    "%sB" % size,
                                    name=vendorid,
                                    version=version,
                                    release=release)
                log.info("Files extracted")
        log.debug("Extraction done")
        return new_base

# vim: sw=4 et sts=4:

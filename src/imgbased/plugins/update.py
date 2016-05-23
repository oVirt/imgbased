
import glob
import logging
import os
from .. import local
from ..bootloader import Grubby
from ..naming import Image
from ..utils import size_of_fstree, mounted, Filesystem, Rsync, \
    BuildMetadata

log = logging.getLogger(__package__)


class UpdateConfigurationSection(local.Configuration.Section):
    _type = "update"
    images_to_keep = 2


def init(app):
    app.hooks.connect("pre-arg-parse", add_argparse)
    app.hooks.connect("post-arg-parse", post_argparse)

    local.Configuration.register_section(UpdateConfigurationSection)


def add_argparse(app, parser, subparsers):
    """Add our argparser bit's to the overall parser
    It will be called when the app is launched
    """
    u = subparsers.add_parser("update",
                              help="Update handling")

    u.add_argument("--format", default="liveimg")
    u.add_argument("FILENAME")

    r = subparsers.add_parser("rollback",
                              help="Rollback layer operation")
    r.add_argument("--to", nargs="?",
                   help="Explicitly define the NVR to roll back to")


def post_argparse(app, args):
    """Check if we were asked to do something
    It will be called when the user selects a sub-command
    """

    if args.command == "rollback":
        rollback(app, args.to)

    elif args.command == "update":
        if args.format == "liveimg":
            LiveimgExtractor(app.imgbase)\
                .extract(args.FILENAME)
            log.info("Update was pulled successfully")

            keep = app.imgbase.config.section("update").images_to_keep
            GarbageCollector(app.imgbase).run(keep=keep)
        else:
            log.error("Unknown update format %r" % args.format)


class LiveimgExtractor():
    imgbase = None
    can_pipe = False

    def __init__(self, imgbase):
        self.imgbase = imgbase

    def _recommend_size_for_tree(self, path, scale=2.0):
        scaled = size_of_fstree(path) * scale
        remainder = scaled % 512
        return int(scaled + (512 - remainder))

    def add_base_with_tree(self, sourcetree, size, nvr, lvs=None):
        if not os.path.exists(sourcetree):
            raise RuntimeError("Sourcetree does not exist: %s" % sourcetree)

        new_base = self.imgbase.add_base(size,
                                         nvr,
                                         lvs)
        new_base_lv = self.imgbase._lvm_from_layer(new_base)

        with new_base_lv.unprotected():
            log.info("Creating new filesystem on base")
            Filesystem.from_mountpoint("/").mkfs(new_base_lv.path)

            log.info("Writing tree to base")
            with mounted(new_base_lv.path) as mount:
                dst = mount.target + "/"
                rsync = Rsync()
                rsync.sync(sourcetree, dst)
                log.debug("Trying to copy prev fstab")

        new_layer_lv = self.imgbase.add_layer(new_base)

        return (new_base_lv, new_layer_lv)

    def extract(self, liveimgfile, nvr=None):
        new_base = None
        log.info("Extracting image '%s'" % liveimgfile)
        with mounted(liveimgfile) as squashfs:
            log.debug("Mounted squashfs")
            liveimg = glob.glob(squashfs.target + "/*/*.img").pop()
            log.debug("Found fsimage at '%s'" % liveimg)
            with mounted(liveimg) as rootfs:
                nvr = nvr or BuildMetadata(rootfs.target).get("nvr")
                log.debug("Using nvr: %s" % nvr)
                size = self._recommend_size_for_tree(rootfs.target, 3.0)
                log.debug("Recommeneded base size: %s" % size)
                log.info("Starting base creation")
                add_tree = self.add_base_with_tree
                new_base = add_tree(rootfs.target,
                                    "%sB" % size, nvr)
                log.info("Files extracted")
        log.debug("Extraction done")
        return new_base


def rollback(app, specific_nvr):
    """
    The rollback operation will trigger the rollback from the
    current layer to layer before (NVR-1). However, users might specific
    the layer they want to rollback providing the NVR in rollback --to option.
    """

    if len(app.imgbase.naming.layers()) <= 1:
        log.info("It's required to have at least two layers available to"
                 " execute rollback operation!")
        return

    current_layer = app.imgbase.current_layer()
    if specific_nvr is None:
        rollbackto = app.imgbase.naming.layer_before(current_layer)
    else:
        rollbackto = Image.from_nvr(specific_nvr)

    if current_layer == rollbackto:
        log.info("Can't roll back to %s" % rollbackto)
        log.info("You are on %s" % current_layer)
        log.info("The current layer and the rollback layer are the same!")
        log.info("The system layout is:")
        log.info(app.imgbase.layout())
        return

    log.info("You are on %s.." % current_layer)
    log.info("Rollback to %s.." % rollbackto)
    # FIXME: Hide Grubby implementation
    try:
        Grubby().set_default(str(rollbackto))
    except KeyError:
        log.error("Unable to find grub entry for %s" % rollbackto)
        raise

    log.info("This change will take effect after a reboot!")


class GarbageCollector():
    """The garbage collector will remove old updates
    The naming order can be used to find the oldest images
    """
    imgbase = None

    def __init__(self, imgbase):
        self.imgbase = imgbase

    def run(self, keep):
        log.info("Starting garbage collection")

        assert keep > 0

        bases = sorted(self.imgbase.naming.bases())

        if len(bases) <= keep:
            log.info("No bases to free")
            return

        current_layer = self.imgbase.current_layer()
        remove_bases = self._filter_overflow(bases, current_layer.base, keep)

        for base in remove_bases:
            log.info("Freeing %s" % base)
            self.imgbase.remove_base(base.nvr)

        log.info("Garbage collection done.")

    def _filter_candidates(self, bases, current_layer_base, keep):
        """

        >>> gc = GarbageCollector(None)
        >>> bases = [1, 2, 3]
        >>> keep = 2

        >>> cur = 1
        >>> gc._filter_candidates(bases, cur, keep)
        []

        >>> cur = 2
        >>> gc._filter_candidates(bases, cur, keep)
        [1]

        >>> cur = 3
        >>> gc._filter_candidates(bases, cur, keep)
        [1]

        """
        bases_to_keep = bases[-keep:]
        bases_to_free = bases[:-keep]

        log.debug("Keeping bases: %s" % bases_to_keep)
        log.debug("Freeing bases: %s" % bases_to_free)

        remove_bases = []

        for base in bases_to_free:
            if base == current_layer_base:
                log.info("Not freeing %s, because it is in use" % base)
                continue
            remove_bases.append(base)

        return remove_bases

# vim: sw=4 et sts=4:

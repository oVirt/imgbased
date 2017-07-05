
import glob
import logging
import os

from .. import local
from ..bootloader import BootConfiguration
from ..naming import Image
from ..utils import mounted, Filesystem, BuildMetadata, Tar

log = logging.getLogger(__package__)


class UpdateConfigurationSection(local.Configuration.Section):
    _type = "update"
    images_to_keep = 2


class RollbackFailedError(Exception):
    pass


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
            base_lv, _ = LiveimgExtractor(app.imgbase).extract(args.FILENAME)
            log.info("Update was pulled successfully")
            keep = app.imgbase.config.section("update").images_to_keep
            GarbageCollector(app.imgbase).run(base_lv, keep)
        else:
            log.error("Unknown update format %r" % args.format)


class LiveimgExtractor():
    imgbase = None
    can_pipe = False

    def __init__(self, imgbase):
        self.imgbase = imgbase

    def _recommend_size_for_tree(self):
        # Get the size of the current layer and use that
        # so each new layer is the size of the last one
        size = self.imgbase.lv_from_layer(
            self.imgbase.current_layer()).size_bytes
        return size

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
                tar = Tar()
                tar.sync(sourcetree, dst)
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
                size = self._recommend_size_for_tree()
                log.debug("Recommeneded base size: %s" % size)
                log.info("Starting base creation")
                add_tree = self.add_base_with_tree
                new_base = add_tree(rootfs.target,
                                    "%s" % size, nvr)
                log.info("Files extracted")
        log.debug("Extraction done")
        return new_base


def rollback(app, specific_nvr):
    """
    The rollback operation will trigger the rollback from the
    current layer to layer before (NVR-1). However, users might specific
    the layer they want to rollback providing the NVR in rollback --to option.
    """

    dst_layer = None

    if len(app.imgbase.naming.layers()) <= 1:
        log.error("It's required to have at least two layers available to"
                  " execute rollback operation!")
        raise RollbackFailedError()

    current_layer = app.imgbase.current_layer()
    if specific_nvr is None:
        dst_layer = app.imgbase.naming.layer_before(current_layer)
    else:
        dst_layer = Image.from_nvr(specific_nvr)

    if current_layer == dst_layer:
        log.err("Can't roll back to %s" % dst_layer)
        log.info("You are on %s" % current_layer)
        log.info("The current layer and the rollback layer are the same!")
        log.info("The system layout is:")
        log.info(app.imgbase.layout())
        raise RollbackFailedError()

    log.info("You are on %s.." % current_layer)
    log.info("Rollback to %s.." % dst_layer)
    # FIXME: Hide Grubby implementation
    try:
        BootConfiguration().set_default(dst_layer)
    except KeyError:
        log.error("Unable to find boot entry for %s" % dst_layer)
        raise

    log.info("Rollback was successful")
    log.info("This change will take effect after a reboot!")

    return dst_layer


class GarbageCollector():
    """The garbage collector will remove old updates
    The naming order can be used to find the oldest images
    """
    imgbase = None

    def __init__(self, imgbase):
        self.imgbase = imgbase

    def run(self, new_base_lv, keep):
        log.info("Starting garbage collection")

        assert keep > 0

        bases = sorted(self.imgbase.naming.bases())

        if len(bases) <= keep:
            log.info("No bases to free")
            return

        current_layer = self.imgbase.current_layer()
        new_base = Image.from_lv_name(new_base_lv.lv_name)
        remove_bases = self._filter_candidates(bases, current_layer.base,
                                               new_base, keep)

        for base in remove_bases:
            log.info("Freeing %s" % base)
            self.imgbase.remove_base(base.nvr)

        log.info("Garbage collection done.")

    def _filter_candidates(self, bases, current_layer_base, new_base, keep):
        """

        >>> gc = GarbageCollector(None)
        >>> bases = [1, 2, 3]
        >>> keep = 2
        >>> new_base = 3

        >>> cur = 1
        >>> gc._filter_candidates(bases, cur, new_base, keep)
        [2]

        >>> cur = 2
        >>> gc._filter_candidates(bases, cur, new_base, keep)
        [1]

        >>> cur = 3
        >>> gc._filter_candidates(bases, cur, new_base, keep)
        [1]

        """
        bases_to_keep = {current_layer_base, new_base}
        keep_extra = keep - len(bases_to_keep)
        if keep_extra > 0:
            extra_bases = sorted(set(bases) - bases_to_keep)
            bases_to_keep.update(extra_bases[-keep_extra:])
        bases_to_free = [b for b in bases if b not in bases_to_keep]

        log.debug("Keeping bases: %s" % bases_to_keep)
        log.debug("Freeing bases: %s" % bases_to_free)

        return bases_to_free

# vim: sw=4 et sts=4:

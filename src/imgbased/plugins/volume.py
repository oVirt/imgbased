
import logging
import os
from ..lvm import LVM
from ..utils import mounted, systemctl, File, mkfs, \
    Rsync


log = logging.getLogger(__package__)


def init(app):
    app.hooks.connect("pre-arg-parse", add_argparse)
    app.hooks.connect("post-arg-parse", check_argparse)


def add_argparse(app, parser, subparsers):
    if not app.experimental:
        return

    s = subparsers.add_parser("volume",
                              help="Volume management")
    s.add_argument("--list", action="store_true",
                   help="List all known volumnes")
    s.add_argument("--attach", metavar="PATH",
                   help="Attach a volume to the current layer")
    s.add_argument("--detach", metavar="PATH",
                   help="Detach a volume from the current layer")
    s.add_argument("--create", nargs=2, metavar=("PATH", "SIZE"),
                   help="Create a volume of SIZE for PATH")
    s.add_argument("--remove", metavar="PATH",
                   help="Remove the volume for PATH")


def check_argparse(app, args):
    log.debug("Operating on: %s" % app.imgbase)
    if args.command == "volume":
        vols = Volumes(app.imgbase)
        if args.list:
            for v in vols.volumes():
                print(v)
        elif args.create:
            where, size = args.create
            vols.create(where, size)
        elif args.remove:
            vols.remove(args.remove)
        elif args.attach:
            vols.attach(args.attach)
        elif args.detach:
            vols.detach(args.detach)


class Volumes(object):
    tag_volume = "imgbased:volume"

    imgbase = None

    mountfile_tmpl = """# Created by imgbased
[Mount]
What={what}
Where={where}
Options={options}
SloppyOptions=yes

[Install]
WantedBy=local-fs.target
"""

    automountfile_tmpl = """# Created by imgbased
[Automount]
Where={where}

[Install]
WantedBy=local-fs.target
"""

    def __init__(self, imgbase):
        self.imgbase = imgbase

    def volumes(self):
        lvs = LVM.LV.find_by_tag(self.tag_volume)
        return ["/" + lv.lv_name.replace("-", "/").replace("//", "-")
                for lv in lvs]

    def is_volume(self, where):
        return where.rstrip("/") in self.volumes()

    def _volname(self, where):
        return where.strip("/").replace("-", "--").replace("/", "-")

    def _mountfilename(self, where, unittype):
        safewhere = self._volname(where)
        return "/etc/systemd/system/%s.%s" % (safewhere, unittype)

    def create(self, where, size):
        assert not self.is_volume(where), \
            "Path is already a volume: %s" % where
        assert where.startswith("/"), "An absolute path is required"
        assert os.path.isdir(where), "Is no dir: %s" % where

        volname = self._volname(where)

        # Create the vol
        vol = self.imgbase._thinpool().create_thinvol(volname, size)
        vol.addtag(self.tag_volume)

        mkfs(vol.path)

        # Populate
        with mounted(vol.path) as mount:
            Rsync().sync(where + "/", mount.target.rstrip("/"))
            pass

        log.info("Volume for '%s' was created successful" % where)
        self.attach(where)

    def remove(self, where):
        assert self.is_volume(where), "Path is no volume: %s" % where

        log.warn("Removing the volume will also remove the data "
                 "on that volume.")

        volname = self._volname(where)
        self.detach(where)
        LVM.LV(self.imgbase._vg(), volname).remove()

        log.info("Volume for '%s' was removed successful" % where)

    def attach(self, where):
        assert self.is_volume(where), "Path is no volume: %s" % where

        volname = self._volname(where)
        what = "/dev/%s/%s" % (self.imgbase._vg(), volname)
        f = File(self._mountfilename(where, "mount"))
        f.write(self.mountfile_tmpl.format(what=what,
                                           where=where,
                                           options="discard"))

        automountunitfile = self._mountfilename(where, "automount")
        automountunit = os.path.basename(automountunitfile)
        f = File(automountunitfile)
        f.write(self.automountfile_tmpl.format(where=where))

        systemctl.daemon_reload()

        systemctl.enable(automountunit)
        systemctl.start(automountunit)

        # Access it to start it
        os.listdir(where)

        log.info("Volume for '%s' was attached successful" % where)

    def detach(self, where):
        assert self.is_volume(where), "Path is no volume: %s" % where

        mount = self._mountfilename(where, "mount")
        automount = self._mountfilename(where, "automount")

        for unitfile in [automount, mount]:
            unit = os.path.basename(unitfile)
            systemctl.disable(unit)
            systemctl.stop(unit)
            File(unitfile).remove()

        systemctl.daemon_reload()

        log.info("Volume for '%s' was detached successful" % where)

# vim: sw=4 et sts=4

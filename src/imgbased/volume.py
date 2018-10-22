import logging
import os
import time
from .lvm import LVM
from .utils import mounted, systemctl, File, mkfs, Rsync


log = logging.getLogger(__package__)


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

    def __init__(self, imgbase):
        self.imgbase = imgbase

    def volumes(self):
        lvs = LVM.LV.find_by_tag(self.tag_volume)
        return ["/" + lv.lv_name.replace("_", "/").replace("--", "-")
                for lv in lvs]

    def is_volume(self, where):
        return where.rstrip("/") in self.volumes()

    def _volname(self, where):
        return where.strip("/").replace("-", "--").replace("/", "_")

    def _mountfile(self, where, unittype="mount"):
        safewhere = self._volname(where).replace("_", "-")
        return File("/etc/systemd/system/%s.%s" % (safewhere, unittype))

    def _rename_volume(self, thinpool, volname):
        new_name = "%s.%s" % (volname, time.strftime("%Y%m%d%H%M%S"))
        lv = LVM.LV.from_lv_name(thinpool.vg_name, volname)
        lv.rename(new_name)
        lv.deltag(self.tag_volume)

    def create(self, where, size, attach_now=True):
        assert where.startswith("/"), "An absolute path is required"
        assert os.path.isdir(where), "Is no dir: %s" % where

        thinpool = self.imgbase._thinpool()
        volname = self._volname(where)

        if self.is_volume(where):
            self._rename_volume(thinpool, volname)

        # Create the vol
        vol = thinpool.create_thinvol(volname, size)
        vol.addtag(self.tag_volume)

        mkfs(vol.path)

        # Populate
        with mounted(vol.path) as mount:
            Rsync().sync(where + "/", mount.target.rstrip("/"))
            pass

        log.info("Volume for '%s' was created successful" % where)
        self.attach(where, attach_now)

    def remove(self, where, force=False):
        assert self.is_volume(where), "Path is no volume: %s" % where

        log.warn("Removing the volume will also remove the data "
                 "on that volume.")

        volname = self._volname(where)
        self.detach(where)
        self.imgbase.lv(volname).remove(force)

        log.info("Volume for '%s' was removed successful" % where)

    def attach(self, where, attach_now):
        assert self.is_volume(where), "Path is no volume: %s" % where

        volname = self._volname(where)
        what = self.imgbase.lv(volname).path

        unitfile = self._mountfile(where)
        unitfile.write(self.mountfile_tmpl.format(what=what,
                                                  where=where,
                                                  options="discard"))

        systemctl.daemon_reload()

        systemctl.enable(unitfile.basename())
        if attach_now:
            systemctl.start(unitfile.basename())

            # Access it to start it
            os.listdir(where)

            log.info("Volume for '%s' was attached successful" % where)
        else:
            log.info("Volume for '%s' was created but not attached" % where)

    def detach(self, where):
        assert self.is_volume(where), "Path is no volume: %s" % where

        unitfile = self._mountfile(where)

        systemctl.disable(unitfile.basename())
        systemctl.stop(unitfile.basename())
        unitfile.remove()

        systemctl.daemon_reload()

        log.info("Volume for '%s' was detached successful" % where)

# vim: sw=4 et sts=4

#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# imgbase
#
# Copyright (C) 2014-2021  Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Author(s): Fabian Deutsch <fabiand@redhat.com>
#

import glob
import logging
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import traceback
from contextlib import contextmanager

from queue import Queue

from . import command, constants

log = logging.getLogger(__package__)


try:
    string_types = [str, unicode, bytes]
except NameError:
    string_types = [str, bytes]


class FilesystemNotSupported(Exception):
    pass


def remove_file(path, dir=False, *args):
    args = list(args) + ["-f", path]
    args = args + ["-r"] if dir else args
    rm = ExternalBinary().rm
    return rm(args)


def copy_files(dst, srcs, *args):
    """Copy files

    Use the native copy command to also copy xattrs (for SELinux)
    """
    args = list(args) + srcs + [dst]
    cp = ExternalBinary().cp
    return cp(args)


def safe_copy_file(src, dst):
    log.debug("safe_copy_file: %s to %s", src, dst)
    dname = os.path.dirname(dst)
    fname = dst
    if os.path.isdir(dst):
        dname = dst
        fname = dst + "/" + os.path.basename(src)
    tmp = tempfile.mktemp(dir=dname, prefix=constants.IMGBASED_TMPFILE_PREFIX)
    shutil.copy2(src, tmp)
    os.rename(tmp, fname)


def grub_cfg_path():
    grub_efi_cfg = "/etc/grub2-efi.cfg"
    if os.path.isdir("/sys/firmware/efi") and os.path.exists(grub_efi_cfg):
        return os.path.realpath(grub_efi_cfg)
    grub_cfg = "/etc/grub2.cfg"
    if os.path.exists(grub_cfg):
        return os.path.realpath(grub_cfg)
    raise RuntimeError("No grub conf found")


def safe_grub_call(func):
    def wrapper(*args, **kwargs):
        grubcfg = grub_cfg_path()
        tmpcfg = tempfile.mktemp(dir=os.path.dirname(grubcfg),
                                 prefix="grub.cfg.")
        shutil.copy2(grubcfg, tmpcfg)
        try:
            return func(*args, **kwargs)
        finally:
            if os.stat(grubcfg).st_size == 0:
                log.debug("grub call failed, restoring previous grub.cfg")
                shutil.copy2(tmpcfg, grubcfg)
            os.unlink(tmpcfg)
    return wrapper


@safe_grub_call
def grubby(*args, **kwargs):
    return ExternalBinary().grubby(list(args) + ["--bad-image-okay"], **kwargs)


@safe_grub_call
def grub2_mkconfig():
    ExternalBinary().grub2_mkconfig(["-o", grub_cfg_path()])


def grub2_editenv(*args, **kwargs):
    grubenv = os.path.dirname(grub_cfg_path()) + "/grubenv"
    if os.stat(grubenv).st_size != 1024:
        log.warn("Wrong size fo %s, skipping grub2-editenv", grubenv)
        return
    ExternalBinary().grub2_editenv([grubenv] + list(args), **kwargs)


def findmnt(options, path=None, raise_on_error=False):
    opts_cmd = ["-no"] + options
    if path is not None:
        opts_cmd.append(path)
    try:
        return ExternalBinary().findmnt(opts_cmd)
    except Exception:
        if raise_on_error:
            raise


def find_mount_target():
    return findmnt(["TARGET", "-l"]).split()


def find_mount_source(path, raise_on_error=False):
    mnt_source = findmnt(["SOURCE"], path=path, raise_on_error=raise_on_error)
    if mnt_source is not None:
        return mnt_source.strip()
    return None


def get_boot_args():
    cmdline = File("/proc/cmdline").contents
    return dict([(x.split("=", maxsplit=1)+[""])[:2] for x in cmdline.split()])


class MountPoint(object):
    target = None
    tmpdir = None

    def __init__(self, source, options=None, target=None, fstype=None):
        self.run = ExternalBinary()
        self.source = source
        self.options = options
        self.target = target
        self.fstype = fstype

    def mount(self):
        # If no target, then create one
        if not self.target:
            self.tmpdir = \
                self.run.call(["mktemp", "-d", "--tmpdir", "mnt.XXXXX"])
            self.target = self.tmpdir

        # If a custom target, but doesn't exist, create
        if not os.path.exists(self.target):
            self.run.call(["mkdir", "-p", self.target])

        cmd = ["mount"]
        if self.options:
            cmd += ["-o%s" % self.options]
        if self.fstype:
            cmd += ["-t%s" % self.fstype]
        cmd += [self.source, self.target]
        self.run.call(cmd)

    def umount(self):
        if self.options is not None and "rbind" in self.options:
            self.run.call(["umount", "-R", "-l", self.target])
        else:
            self.run.call(["umount", "-l", self.target])
        if self.tmpdir:
            self.run.call(["rmdir", self.tmpdir])

    def _ismount(self, path):
        return any(
            [current_line for current_line in File('/proc/mounts').lines() if
             current_line.split()[1] == re.sub(r'/+', '/', path)])

    def path(self, subpath):
        """Return the abs path to a path inside this mounted fs
        """
        return self.target + "/" + subpath


class mounted(object):
    def __init__(self, source, options=None, target=None, fstype=None):
        self.mp = MountPoint(source, options, target, fstype)

    def __enter__(self):
        self.mp.mount()
        return self.mp

    def __exit__(self, exc_type, exc_value, tb):
        self.mp.umount()
        return exc_type is None

    def path(self, subpath):
        return self.mp.path(subpath)


@contextmanager
def bindmounted(source, target, rbind=False, readonly=False):
    options = "rbind" if rbind else "bind,private"
    options = options + ",ro" if readonly else options
    with mounted(source, target=target, options=options) as mnt:
        yield mnt
    log.debug("Done!")


class Filesystem():

    @classmethod
    def supported_filesystem(cls):
        return ['ext4', 'xfs']

    @staticmethod
    def get_type(path):
        cmd = ["blkid", "-o", "value", "-s", "TYPE", path]
        return subprocess.check_output(cmd).decode("utf-8").strip()

    @classmethod
    def from_device(cls, path):
        fs_type = cls.get_type(path)

        if fs_type not in cls.supported_filesystem():
            raise FilesystemNotSupported

        if fs_type == 'ext4':
            cls = Ext4

        elif fs_type == 'xfs':
            cls = XFS

        return cls(path)

    @classmethod
    def from_mountpoint(cls, path):
        source = find_mount_source(path, raise_on_error=True)
        assert source
        return cls.from_device(source)

    path = None

    def __init__(self, path):
        self.path = path

    @staticmethod
    def mkfs(path, debug=False):
        raise NotImplementedError

    def randomize_uuid(self):
        raise NotImplementedError


class Ext4(Filesystem):
    @staticmethod
    def mkfs(path, debug=False):
        cmd = ["mkfs.ext4", "-E", "discard", path]
        if not debug:
            cmd.append("-q")
        log.debug("Running: %s" % cmd)
        command.call(cmd, stderr=subprocess.STDOUT)

    def randomize_uuid(self):
        cmd = ["e2fsck", "-y", "-f", self.path]
        log.debug("Running: %s" % cmd)
        try:
            command.call(cmd, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            if e.returncode != 1:  # e2fsck returns 1 if the fs was corrected
                raise
        cmd = ["tune2fs", "-U", "random", self.path]
        log.debug("Running: %s" % cmd)
        command.call(cmd, stderr=subprocess.STDOUT)


class XFS(Filesystem):
    @staticmethod
    def mkfs(path, debug=False):
        cmd = ["mkfs.xfs", path]
        if not debug:
            cmd.append("-q")
        log.debug("Running: %s" % cmd)
        command.call(cmd, stderr=subprocess.STDOUT)

    def randomize_uuid(self):
        with mounted(self.path, options="nouuid"):
            # The fs needs to be mounted once to replay
            # eventual metadata
            pass
        cmd = ["xfs_admin", "-U", "generate", self.path]
        log.debug("Running: %s" % cmd)
        command.call(cmd, stderr=subprocess.STDOUT)


def findls(path):
    return ExternalBinary().find(["-ls"], cwd=path).splitlines(True)


class ExternalBinary(object):
    dry = False
    squash_output = False

    def call(self, *args, **kwargs):
        stdout = bytes()
        if not self.dry:
            stdout = command.call(*args, **kwargs)
            if stdout and not self.squash_output:
                log.debug("Returned: %s" % stdout[0:1024])
        return stdout.decode(errors="replace").strip()

    def lvs(self, args, **kwargs):
        return self.call(["lvs"] + args, **kwargs)

    def vgs(self, args, **kwargs):
        return self.call(["vgs"] + args, **kwargs)

    def lvcreate(self, args, **kwargs):
        return self.call(["lvcreate"] + args, **kwargs)

    def lvremove(self, args, **kwargs):
        return self.call(["lvremove"] + args, **kwargs)

    def lvrename(self, args, **kwargs):
        return self.call(["lvrename"] + args, **kwargs)

    def lvextend(self, args, **kwargs):
        return self.call(["lvextend"] + args, **kwargs)

    def vgcreate(self, args, **kwargs):
        return self.call(["vgcreate"] + args, **kwargs)

    def lvchange(self, args, **kwargs):
        return self.call(["lvchange"] + args, **kwargs)

    def vgchange(self, args, **kwargs):
        return self.call(["vgchange"] + args, **kwargs)

    def find(self, args, **kwargs):
        return self.call(["find"] + args, **kwargs)

    def findmnt(self, args, **kwargs):
        return self.call(["findmnt"] + args, **kwargs)

    def du(self, args, **kwargs):
        return self.call(["du"] + args, **kwargs)

    def rm(self, args, **kwargs):
        return self.call(["rm"] + args, **kwargs)

    def cp(self, args, **kwargs):
        return self.call(["cp"] + args, **kwargs)

    def rpm(self, args, **kwargs):
        self.squash_output = True
        return self.call(["rpm"] + args, **kwargs)

    def grubby(self, args, **kwargs):
        return self.call(["grubby"] + args, **kwargs)

    def grub2_mkconfig(self, args, **kwargs):
        return self.call(["grub2-mkconfig"] + args, **kwargs)

    def grub2_editenv(self, args, **kwargs):
        return self.call(["grub2-editenv"] + args, **kwargs)

    def systemctl(self, args, **kwargs):
        return self.call(["systemctl"] + args, **kwargs)

    def pkill(self, args, **kwargs):
        return self.call(["pkill"] + args, **kwargs)

    def umount(self, args, **kwargs):
        return self.call(["umount", "-l"] + args, **kwargs)

    def semanage(self, args, **kwargs):
        return self.call(["semanage"] + args, **kwargs)

    def runcon(self, args, **kwargs):
        return self.call(["runcon"] + args, **kwargs)

    def lvmconfig(self, args, **kwargs):
        return self.call(["lvmconfig"] + args, **kwargs)

    def mount(self, args, **kwargs):
        return self.call(["mount"] + args, **kwargs)

    def getenforce(self):
        return self.call(["getenforce"])

    def mknod(self, args, **kwargs):
        return self.call(["mknod"] + args, **kwargs)

    def ldconfig(self, args, **kwargs):
        return self.call(["ldconfig"] + args, **kwargs)

    def sync(self, args, **kwargs):
        return self.call(["sync"] + args, **kwargs)


class LvmBinary(ExternalBinary):
    def call(self, *args, **kwargs):
        with open(os.devnull, "w") as DEVNULL:
            return super(LvmBinary, self).call(*args, stderr=DEVNULL, **kwargs)


class LvmCLI():
    lvs = LvmBinary().lvs
    vgs = LvmBinary().vgs
    lvcreate = ExternalBinary().lvcreate
    lvchange = LvmBinary().lvchange
    lvremove = LvmBinary().lvremove
    lvrename = LvmBinary().lvrename
    lvextend = LvmBinary().lvextend
    vgcreate = LvmBinary().vgcreate
    vgchange = LvmBinary().vgchange
    lvmconfig = LvmBinary().lvmconfig


class SELinux(object):
    SELINUX_DISABLED = "Disabled"
    SELINUX_ENFORCING = "Enforcing"
    SELINUX_PERMISSIVE = "Permissive"

    @staticmethod
    def mode():
        return ExternalBinary().getenforce()

    @staticmethod
    def disabled(mode=None):
        mode = mode or SELinux.mode()
        return (mode == SELinux.SELINUX_DISABLED)

    @staticmethod
    def enabled(mode=None):
        return (not SELinux.disabled(mode))

    @staticmethod
    def permissive(mode=None):
        mode = mode or SELinux.mode()
        return (mode == SELinux.SELINUX_PERMISSIVE)

    @staticmethod
    def enforcing(mode=None):
        mode = mode or SELinux.mode()
        return (mode == SELinux.SELINUX_ENFORCING)


class SELinuxDomain(object):
    run = ExternalBinary()

    def __init__(self, domain):
        self._domain = domain
        self._mode = SELinux.mode()
        self._exists = self._check_domain()

    def _check_domain(self):
        """
        Checks if the domain is permissive, or if SELinux is disabled.  If any
        of the the checks are True, we should not call `semanage permissive`.
        """
        if SELinux.disabled(self._mode) or SELinux.permissive(self._mode):
            return True
        domains = self.run.semanage(["permissive", "-nl"])
        return self._domain in domains.split()

    def __enter__(self):
        if not self._exists:
            self.run.semanage(["permissive", "-a", self._domain])
        return self

    def __exit__(self, exc_type, exc_value, tb):
        if self._exists:
            return
        self.run.semanage(["permissive", "-d", self._domain])

    def runcon(self, args):
        if SELinux.disabled(self._mode):
            return
        self.run.runcon(["-t", self._domain, "--"] + args)


class File(object):
    filename = None

    @property
    def contents(self):
        return self.read()

    @property
    def stat(self):
        return os.stat(self.filename)

    def __init__(self, fn):
        self.filename = fn

    def __str__(self):
        return "<%s %s>" % (self.__class__.__name__, self.filename)

    def read(self):
        with open(self.filename) as src:
            return src.read()

    def exists(self):
        return os.path.exists(self.filename)

    def replace(self, pat, repl):
        self.write(self.contents.replace(pat, repl))

    def sub(self, pat, repl):
        self.write(re.sub(pat, repl, self.contents))

    def write(self, data, mode="w", mkdir=False):
        if mkdir:
            os.makedirs(os.path.dirname(self.filename))
        with open(self.filename, mode) as dst:
            dst.write(data)

    def writen(self, data, mode="w"):
        self.write(data + "\n", mode)

    def remove(self):
        os.unlink(self.filename)

    def lines(self, keepends=False):
        for line in self.contents.splitlines(keepends):
            yield line

    def findall(self, pat):
        r = []
        for line in self.lines():
            r += re.findall(pat, line)
        return r

    def chmod(self, mode):
        return os.chmod(self.filename, mode)

    def basename(self):
        return os.path.basename(self.filename)

    def truncate(self, size=0):
        """Truncate the file to size
        """
        with open(self.filename, "w") as fd:
            fd.truncate(size)


class Fstab(File):
    _testdata = """#
# /etc/fstab
# Created by anaconda on Fri Jun  5 11:25:14 2015
#
# Accessible filesystems, by reference, are maintained ...
# See man pages fstab(5), findfs(8), mount(8) and/or ...
#
<root> / ext4 defaults,discard 1 1
<boot> /boot ext4 defaults 1 2
<swap> swap swap defaults 0 0
"""

    class Entry():
        _index = None
        source = None
        target = None
        fs = None
        options = []

        def __repr__(self):
            return ("<Entry {self._index} {self.source} {self.target} "
                    "{self.fs} {self.options} />")\
                .format(self=self)

    def _read(self):
        return self.contents

    def parse(self):
        """
        >>> fstab = Fstab(None)
        >>> fstab._read = lambda: Fstab._testdata
        >>> fstab.parse()
        [<Entry / <root> / ext4 ['defaults', 'discard'] />, \
<Entry /boot <boot> /boot ext4 ['defaults'] />, \
<Entry swap <swap> swap swap ['defaults'] />]
        """
        entries = []
        data = self._read()
        for line in data.splitlines():
            if line.startswith("#") or line.strip() == "":
                continue
            source, target, fs, options = shlex.split(line)[:4]
            entry = Fstab.Entry()
            entry._index = target  # target is unique
            entry.source = source
            entry.target = target
            entry.fs = fs
            entry.options = options.split(",")
            entries.append(entry)

        return sorted(entries, key=lambda e: e._index)

    def update(self, entry):
        """
        >>> Fstab._read = lambda x: Fstab._testdata
        >>> def printer(args):
        ...     Fstab._testdata = args
        ...     print(args)
        >>> fstab = Fstab(None)
        >>> fstab.writen = printer
        >>> entries = fstab.parse()
        >>> entry = entries[0]
        >>> entry.source = "foo"
        >>> fstab.update(entry)
        #
        # /etc/fstab
        # Created by anaconda on Fri Jun  5 11:25:14 2015
        #
        # Accessible filesystems, by reference, are maintained ...
        # See man pages fstab(5), findfs(8), mount(8) and/or ...
        #
        foo / ext4 defaults,discard 1 1
        <boot> /boot ext4 defaults 1 2
        <swap> swap swap defaults 0 0

        >>> entry.target = "bar"
        >>> fstab.update(entry)
        #
        # /etc/fstab
        # Created by anaconda on Fri Jun  5 11:25:14 2015
        #
        # Accessible filesystems, by reference, are maintained ...
        # See man pages fstab(5), findfs(8), mount(8) and/or ...
        #
        foo bar ext4 defaults,discard 1 1
        <boot> /boot ext4 defaults 1 2
        <swap> swap swap defaults 0 0

        >>> entry = entries[1]
        >>> entry.target = "bar"
        >>> fstab.update(entry)
        #
        # /etc/fstab
        # Created by anaconda on Fri Jun  5 11:25:14 2015
        #
        # Accessible filesystems, by reference, are maintained ...
        # See man pages fstab(5), findfs(8), mount(8) and/or ...
        #
        foo bar ext4 defaults,discard 1 1
        <boot> bar ext4 defaults 1 2
        <swap> swap swap defaults 0 0
        """
        log.debug("Got new fstab entry: %s" % entry)
        data = self._read()
        newdata = []
        for line in data.strip().splitlines():
            if line.strip() == "" or line.startswith("#"):
                newdata.append(line)
                continue
            tokens = shlex.split(line)
            if tokens[1] == entry._index:
                tokens[0] = entry.source
                tokens[1] = entry.target
                tokens[2] = entry.fs
                tokens[3] = ",".join(entry.options)
                newdata.append(" ".join(tokens))
            else:
                newdata.append(line)
        self.writen("\n".join(newdata))

    def by_source(self, source=None):
        """
        >>> Fstab._read = lambda x: Fstab._testdata
        >>> fstab = Fstab(None)
        >>> sorted(fstab.by_source().items())
        [('<boot>', <Entry /boot <boot> /boot ext4 ['defaults'] />), \
('<root>', <Entry / <root> / ext4 ['defaults', 'discard'] />), \
('<swap>', <Entry swap <swap> swap swap ['defaults'] />)]
        >>> Fstab(None).by_source('<root>')
        <Entry / <root> / ext4 ['defaults', 'discard'] />
        """
        sources = dict((e.source, e) for e in self.parse())
        if source:
            return sources[source]
        else:
            return sources

    def by_target(self, target=None):
        """
        >>> Fstab._read = lambda x: Fstab._testdata
        >>> fstab = Fstab(None)
        >>> sorted(fstab.by_target().items())
        [('/', <Entry / <root> / ext4 ['defaults', 'discard'] />), \
('/boot', <Entry /boot <boot> /boot ext4 ['defaults'] />), \
('swap', <Entry swap <swap> swap swap ['defaults'] />)]
        >>> Fstab(None).by_target('/')
        <Entry / <root> / ext4 ['defaults', 'discard'] />
        """
        targets = dict((e.target, e) for e in self.parse())
        if target:
            return targets[target]
        else:
            return targets


class ShellVarFile(File):
    def parse(self, data=None):
        """Parse
        >>> testdata= 'VERSION_ID=22\\nPRETTY_NAME="Fedora 22 (Twenty Two)"\\n'
        >>> sorted(ShellVarFile(None).parse(testdata).items())
        [('PRETTY_NAME', 'Fedora 22 (Twenty Two)'), ('VERSION_ID', '22')]

        >>> def printer(*args):
        ...     print(args)
        >>> varfile = ShellVarFile(None)
        >>> varfile.read = lambda: "A=a\\nB=b\\nAh=ah"
        >>> varfile.write = printer
        >>> varfile.contents
        'A=a\\nB=b\\nAh=ah'
        >>> varfile.set("A", "1")
        ("A='1'\\nB=b\\nAh=ah",)
        """
        data = data or self.contents

        parsed = {}
        try:
            for line in data.splitlines(False):
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                parsed[key] = val.strip('"').strip("'")
        except Exception:
            log.error("Failed to parse: %s" % line)
            raise
        return parsed

    def get(self, key, default):
        return self.parse().get(key, default)

    def set(self, key, val, force=False):
        self.sub(r"%s=.*" % key, "%s=%r" % (key, str(val)))
        if force:
            if not self.get(key, None):
                self.write("%s=%r\n" % (key, str(val)), mode="a")


class Motd(File):
    def run_motd(self, is_ok, do_update):
        motd = self._motdgen(is_ok)
        if do_update:
            self.write(motd + "\n")
        print(motd)

    def clear_motd(self):
        if self.exists():
            self.replace(self._motdgen(True)+"\n", "")
            self.replace(self._motdgen(False)+"\n", "")

    def _motdgen(self, is_ok):
        txts = [""]
        if not is_ok:
            txts += ["  imgbase status: " + bcolors.fail("DEGRADED")]
            txts += ["  Please check the status manually using"
                     " `imgbase check`"]
        else:
            txts += ["  imgbase status: " + bcolors.ok("OK")]
        txts += [""]
        return "\n".join(txts)


def fileMappedPropperty(key, default=None):
    """Can be used to create "mapped" properties

    The benefit compared to __get and __setattr__ is that
    by explicitly defining the properties, it is obvious
    by looking at the class what properties get exported
    and it is also clear what default will be used - and
    if a default is allowed or not (in that case it is mandatory)
    that the variable is defined in the file.

    >>> class Example(ShellVarFile):
    ...    # No default, KeyError if not set
    ...    A = fileMappedPropperty("a")
    ...    # Defaults to "", returned if unset
    ...    B = fileMappedPropperty("b", "")

    >>> data = {"a": 1, "b": 2}
    >>> example = Example("")
    >>> example.parse = lambda: data
    >>> example.set = lambda k, v: data.update({k: v})

    >>> (example.A, example.B)
    (1, 2)

    >>> data = {}
    >>> example.A
    Traceback (most recent call last):
    ...
    KeyError: 'a'
    >>> example.B
    ''

    >>> example.A = 1
    >>> example.A
    1

    >>> example.B = 2
    >>> example.B
    2
    """
    def getter(self):
        assert isinstance(self, ShellVarFile), \
            "%s must be an instance of ShelllVarFile" % self
        if default is not None:
            return self.get(key, default)
        else:
            return self.parse()[key]

    def setter(self, v):
        return self.set(key, v)

    return property(getter, setter)


class PackageDb():
    root = None
    dbpath = None

    def get_packages(self):
        raise NotImplementedError

    def get_files(self, pkgs):
        raise NotImplementedError


class RpmPackageDb(PackageDb):
    def _rpm_cmd(self, a):
        rpmdb = self.dbpath or (self.root or "") + "/var/lib/rpm"
        for dbf in glob.glob(rpmdb + "/__db*"):
            os.unlink(dbf)
        return ExternalBinary().rpm(a)

    def _rpm(self, *args, **kwargs):
        if self.root:
            args += ("--root", self.root)
        if self.dbpath:
            args += ("--dbpath", self.dbpath)
        return self._rpm_cmd(list(args)).splitlines(False)

    def _get_files_by_tag(self, rpms, tag):
        return {k: v for k, v in self.get_file_flags(rpms).items() if tag in v}

    def _split_file_line(self, line):
        attrs, fname = line.split("/", 1)
        return ("/" + fname.strip(), attrs.strip())

    def get_file_flags(self, rpms):
        output = self._rpm("-q", "--queryformat",
                           "[%{FILEFLAGS:fflags} %{FILENAMES}\n]", *rpms)
        return dict([self._split_file_line(x) for x in output])

    def get_verify(self, rpms):
        try:
            output = self._rpm("-V", *rpms)
        except subprocess.CalledProcessError as e:
            output = e.output.decode(errors="replace").splitlines()
            log.debug("Subprocess exception ignored")
        return dict([self._split_file_line(x) for x in output])

    def get_query_files(self, files):
        try:
            output = self._rpm("-qf", *files)
        except subprocess.CalledProcessError as e:
            output = e.output.decode(errors="replace").splitlines()
            log.debug("Subprocess exception ignored")
        not_owned = [x for x in output if "not owned" in x]
        rpms = list(set([x for x in output if x not in not_owned]))
        return (rpms, list(set([x.split()[1] for x in not_owned])))

    def get_conf_files(self, rpms):
        return self._get_files_by_tag(rpms, "c")

    def get_ghost_files(self, rpms):
        return self._get_files_by_tag(rpms, "g")

    def get_packages(self, filter="", exclude=None):
        rpms = [p for p in self._rpm("-qa") if filter in p]

        return [p for p in rpms if exclude not in p] if exclude is not None \
            else rpms

    def get_whatprovides(self, cap):
        return self._rpm("-q", "--qf",
                         "%{name}-%{version}-%{release}.%{arch}\\n",
                         "--whatprovides", cap)

    def get_files(self, pkgs):
        return self._rpm("-ql", *pkgs)

    def get_nvr(self, pkgname):
        return self._rpm("-q", pkgname)

    def get_scripts(self, pkgname):
        return self._rpm("-q", "--scripts", pkgname)

    def get_script_type(self, t):
        scripts = self._rpm("-qa",
                            "--queryformat",
                            '%{{NAME}} @@ %{{{0}}}\\n'.format(t))

        rpms = {}
        pkg = None

        for line in scripts:
            if "@@" in line:
                pkg, begin = [x.strip() for x in line.split('@@')]
                rpms[pkg] = ""
                if begin != "(none)":
                    rpms[pkg] = "{0}\n".format(begin.encode('utf-8'))
            else:
                rpms[pkg] += "{0}\n".format(line.encode('utf-8'))

        return rpms


class systemctl():
    @staticmethod
    def _systemctl(*a):
        return ExternalBinary().systemctl(list(a))

    @staticmethod
    def start(*units):
        systemctl._systemctl("start", *units)

    @staticmethod
    def stop(*units):
        systemctl._systemctl("stop", *units)

    @staticmethod
    def enable(*units):
        systemctl._systemctl("enable", *units)

    @staticmethod
    def disable(*units):
        systemctl._systemctl("disable", *units)

    @staticmethod
    def mask(*units):
        systemctl._systemctl("mask", *units)

    @staticmethod
    def unmask(*units):
        systemctl._systemctl("unmask", *units)

    @staticmethod
    def daemon_reload():
        systemctl._systemctl("daemon-reload")

    @staticmethod
    def status(*units):
        systemctl._systemctl("status", *units)

    @staticmethod
    def is_active(*units):
        try:
            if "inactive" in systemctl._systemctl("is-active", *units):
                return False
        except subprocess.CalledProcessError:
            return False
        return True


class Tar():
    def __init__(self):
        pass

    def sync(self, source, dst):
        default_args = ["--selinux", "--xattrs", "--acls",
                        "--xattrs-include=*", "--warning=no-timestamp"]
        srccmd = ["tar", "cf", "-"] + default_args + ["-C", source, "."]
        log.debug("Calling binary: %s" % srccmd)
        src = subprocess.Popen(srccmd, stdout=subprocess.PIPE)

        dstcmd = ["tar", "xBf", "-"] + default_args + ["-C", dst]
        log.debug("Calling binary: %s" % dstcmd)
        dstproc = subprocess.Popen(dstcmd, stdin=src.stdout)
        dstproc.communicate()
        log.debug("Done syncing new filesystem")


class Rsync():
    checksum_only = False
    existing = False
    update_only = False

    def __init__(
        self,
        checksum_only=False,
        update_only=False,
        exclude=None,
        preserve_owner=True,
    ):
        self.exclude = ["mnt.*/*"] + (exclude or [])
        self.checksum_only = checksum_only
        self.update_only = update_only
        self.preserve_owner = preserve_owner

    def _run(self, cmd):
        log.debug("Running: %s" % cmd)
        command.call(cmd)

    def sync(self, sourcetree, dst):
        assert os.path.isdir(sourcetree), "%s is not a directory" % sourcetree

        self._run(["restorecon", "-Rv", sourcetree])

        cmd = ["rsync"]
        cmd += ["-pAXlHrx"]
        cmd += ["-SWc", "--no-i-r"]
        # cmd += ["--progress"]
        if self.preserve_owner:
            cmd += ["-og"]
        if self.existing:
            cmd += ["--existing"]
        if self.checksum_only:
            cmd += ["--checksum"]
        if self.update_only:
            cmd += ["--update"]
        else:
            cmd += ["-t"]
        if self.exclude:
            for pat in self.exclude:
                cmd += ["--exclude", pat]
        cmd += [sourcetree + "/", dst]

        self._run(cmd)


class IDMap():
    """This class can help to detect uid/gid drift an get it fixed

    uid/gid drift appears in server side generated images/trees, because
    the user and group ids are re-allocated for each build.
    In traditional setups where updates are performed on the client side
    the user/group files are only getting updated, and not written
    from scratch. Thus those systems don't suffer drifts.

    The approach of this class is to

    * detect a drift
    * identify the drift
    * fix the drift on a path

    The class looks at the old and new etc contents, to find how
    the uid/gid for names changed.
    Once a drift is detected, a map is created, mapping the change
    from the old uid/gid to the new uid/gid.
    Then there is a function which will finally fix the drift on a path
    in the new fs to change the uid/gid to map to the names how they are
    in the old user/group file.
    """
    from_etc = None
    to_etc = None
    changed_ids = {}
    _merge_gids = []
    _merge_uids = []

    def __init__(self, from_etc, to_etc):
        self.from_etc = from_etc
        self.to_etc = to_etc
        self._new_ugids = False

    def _parse_ids(self, id_data):
        """foo

        >>> data = '''
        ... root:x:0:0:root:/root:/bin/bash
        ... bin:x:1:1:bin:/bin:/sbin/nologin
        ... daemon:x:2:2:daemon:/sbin:/sbin/nologin
        ... sync:x:5:0:sync:/sbin:/bin/sync
        ... shutdown:x:6:0:shutdown:/sbin:/sbin/shutdown"
        ... '''

        >>> ids = IDMap(None, None)._parse_ids(data)
        >>> sorted(ids.items())
        [('bin', 1), ('daemon', 2), ('root', 0), ('shutdown', 6), \
('sync', 5)]
        """
        idmap = {}
        for line in id_data.splitlines():
            if not line:
                continue
            name, _, _id = line.split(":")[:3]
            idmap[name] = int(_id)
        return idmap

    def _create_idmap(self, from_idmap, to_idmap):
        """

        >>> from_map = {"root": "0", "bin": "1", "adm": "2"}
        >>> to_map = {"root": "0", "bin": "2", "adm": "3"}
        >>> IDMap(None, None)._create_idmap(from_map, to_map)
        [(1, 2), (2, 3)]
        """
        unknown_names = []
        xmap = []
        for fname, fid in from_idmap.items():
            if fname not in to_idmap:
                unknown_names.append(fname)
                continue
            tid = to_idmap[fname]
            if fid != tid:
                log.debug("%s changed from %s to %s" % (fname, fid, tid))
                xmap.append((int(fid), int(tid)))
        return sorted(xmap)

    def _create_idmaps(self, from_uids, from_gids, to_uids, to_gids):
        """

        >>> from_uids = {"root": "0", "bin": "1", "adm": "0"}
        >>> to_uids   = {"root": "0", "bin": "2", "adm": "0"}

        >>> from_gids = {"root": "0", "bin": "1", "adm": "2"}
        >>> to_gids   = {"root": "0", "bin": "2", "adm": "3"}

        >>> IDMap(None, None)._create_idmaps(from_uids, from_gids,
        ... to_uids, to_gids)
        ([(1, 2)], [(1, 2), (2, 3)])
        """

        uidmap = self._create_idmap(from_uids, to_uids)
        gidmap = self._create_idmap(from_gids, to_gids)

        return (uidmap, gidmap)

    def _merge_ids(self, old_content, new_content, li, tracker={}):
        """
        >>> old_content = '''
        ... root:x:0:0:root:/root:/bin/bash
        ... bin:x:1:1:bin:/bin:/sbin/nologin
        ... daemon:x:2:2:daemon:/sbin:/sbin/nologin
        ... sync:x:5:0:sync:/sbin:/bin/sync
        ... shutdown:x:6:0:shutdown:/sbin:/sbin/shutdown
        ... '''
        >>> new_content = '''
        ... root:x:0:0:root:/root:/bin/bash
        ... bin:x:1:1:bin:/bin:/sbin/nologin
        ... daemon:x:2:2:daemon:/sbin:/sbin/nologin
        ... sync:x:5:0:sync:/sbin:/bin/sync
        ... cockpit-ws:x:6:0:shutdown:/sbin:/sbin/nologin
        ... screen:x:8:0:shutdown:/sbin:/sbin/nologin
        ... '''

        >>> content,ids = IDMap(None, None)._merge_ids(
        ... old_content, new_content, [])
        >>> print(content)
        <BLANKLINE>
        root:x:0:0:root:/root:/bin/bash
        bin:x:1:1:bin:/bin:/sbin/nologin
        daemon:x:2:2:daemon:/sbin:/sbin/nologin
        sync:x:5:0:sync:/sbin:/bin/sync
        shutdown:x:6:0:shutdown:/sbin:/sbin/shutdown
        cockpit-ws:x:7:0:shutdown:/sbin:/sbin/nologin
        screen:x:8:0:shutdown:/sbin:/sbin/nologin
        <BLANKLINE>
        >>> ids
        {'6': '7'}
        """
        # TODO: document parameters, not clear what "li" is supposed to be.
        ids = {}
        changed_ids = {}

        def check_id_in_use(i, j):
            return any([i == int(k) for k in j.values()])

        old_lines = old_content.strip().split('\n')
        new_lines = new_content.strip().split('\n')

        for o in old_lines:
            name, _, i = o.split(":")[:3]
            ids[name] = i

        for n in new_lines:
            _write_content = False
            name, _, i = n.split(":")[:3]
            i = int(i)
            if name not in ids:
                _write_content = True
                self._new_ugids = True
                old_id = i
                if not check_id_in_use(i, ids):
                    pass
                else:
                    log.debug("ID in use")
                    while check_id_in_use(i, ids):
                        i += 1
                        if i > 1000:
                            # If it's a system account, do our best to
                            # ensure that it stays as one
                            i = 1
                    fields = n.split(":")
                    i = str(i)
                    fields[2] = i
                    n = ":".join(fields)
                    log.debug("Assigning {} as {}".format(fields[0],
                                                          fields[2]))
                    ids[name] = i
                    changed_ids[str(old_id)] = i
                    li.append((int(i), old_id))

            try:
                fields = n.split(":")
                if fields[3] in tracker:
                    _write_content = True
                    log.debug("GID for {} changed to {}".format(
                        fields[0],
                        tracker[fields[3]]))
                    fields[3] = tracker[fields[3]]
                n = ":".join(fields)

            except IndexError:
                # Not passwd
                pass

            if _write_content:
                log.debug("Adding a new user/group as: {}".format(n))
                old_content += n + "\n"

        return (old_content, changed_ids)

    def _sync_files(self):
        new_groups, ids = self._merge_ids(
            File(self.from_etc + "/group").contents,
            File(self.to_etc + "/group").contents,
            self._merge_gids)
        self.group_content = new_groups
        new_passwd, _ = self._merge_ids(
            File(self.from_etc + "/passwd").contents,
            File(self.to_etc + "/passwd").contents,
            self._merge_uids, ids)
        self.passwd_content = new_passwd

    def get_drift(self):
        """Returns the uid and gid dirft from the old to the new etc
        """

        self._sync_files()

        from_uids = self._parse_ids(File(self.from_etc + "/passwd").contents)
        from_gids = self._parse_ids(File(self.from_etc + "/group").contents)

        to_uids = self._parse_ids(File(self.to_etc + "/passwd").contents)
        to_gids = self._parse_ids(File(self.to_etc + "/group").contents)

        uidmap, gidmap = self._create_idmaps(from_uids, from_gids,
                                             to_uids, to_gids)

        gidmap = gidmap + self._merge_gids
        uidmap = uidmap + self._merge_uids

        return (uidmap, gidmap)

    def has_drift(self):
        """Returns True if the id mapping of a group or user has changed
        """
        return (sum(len(m) for m in self.get_drift()) > 0) or self._new_ugids

    def _map_new_ids_to_old_ids(self, paths_and_ids, _fake_drift=None):
        """Translate all uids/gids in path

        Imagine these paths with their owners:

        >>> old_paths = [("/foo", 40, 2),
        ...              ("/bar", 1, 50),
        ...              ("/nochange", 40, 50),
        ...              ("/allchange", 1, 2)]

        And in the new tree, the uid 1 changed to 11,
        and gid 2 changed to 22:

        >>> new_paths = [("/foo", 40, 22),
        ...              ("/bar", 11, 50),
        ...              ("/nochange", 40, 50),
        ...              ("/allchange", 11, 22)]

        This is described in the drift:

        >>> drift = ([(1, 11)], [(2, 22)])

        Then IDMap will change the ids in the given new path to the old ids.
        This ensures, that the owner does logically not change.

        >>> m = IDMap(None, None)
        >>> changes = m._map_new_ids_to_old_ids(new_paths, drift)
        >>> list(changes)
        [('/foo', (-1, 2)), ('/bar', (1, -1)), ('/allchange', (1, 2))]
        """

        drift = _fake_drift or self.get_drift()
        assert drift

        uidmap, gidmap = map(dict, drift)

        # *map maps from old to new

        rev_uidmap = dict(map(reversed, uidmap.items()))
        rev_gidmap = dict(map(reversed, gidmap.items()))

        # rev*map maps from new to old

        assert len(uidmap) == len(rev_uidmap)
        assert len(gidmap) == len(rev_gidmap)

        for (fn, new_uid, new_gid) in paths_and_ids:
            # Check if for a given id, an old - different - id
            # is known - essentially: if it has changed
            old_uid = rev_uidmap.get(new_uid, -1)
            old_gid = rev_gidmap.get(new_gid, -1)

            if any(v != -1 for v in [old_uid, old_gid]):
                # If there is a change, emit it
                yield (fn, (old_uid, old_gid))

    def fix_drift(self, new_path):
        """This function will walk a tree and adjust all UID/GIDs which drifted

        path is expected to be a path with the new uid/gid.
        """
        # Go through all paths and find their uid/gid
        changed_new_ids = []
        for (dirpath, dirnames, filenames) in os.walk(new_path):
            for fn in dirnames + filenames:
                fullfn = dirpath + "/" + fn
                if not os.path.exists(fullfn):
                    log.debug("File does not exist: %s" % fn)
                    continue
                st = os.stat(fullfn)
                uid = st.st_uid
                gid = st.st_gid
                changed_new_ids.append((fullfn, uid, gid))

        # For each new path, see if the uid/gid changed
        new_ids_xlated_to_old = self._map_new_ids_to_old_ids(changed_new_ids)
        for (fn, old_ids) in new_ids_xlated_to_old:
            # The uid/gid has changed, so change it to the old uid/gid
            try:
                restore_mode = False
                st = os.stat(fn)
                if stat.S_ISDIR(st.st_mode):
                    ftype = "directory"
                elif stat.S_ISREG(st.st_mode):
                    ftype = "file"
                else:
                    ftype = ""
                mode = stat.S_IMODE(st.st_mode)
                log.debug("The mode of {} {} is: {:o}".format(
                    ftype,
                    fn,
                    mode,
                ))
                if (mode & stat.S_ISUID) or (mode & stat.S_ISGID):
                    log.debug("Going to restore the access mode")
                    restore_mode = True
                log.debug("Chowning %r to %s" % (fn, old_ids))
                os.chown(fn, *old_ids)
                if restore_mode:
                    log.debug("Restoring mode of {} {} to: {:o}".format(
                        ftype,
                        fn,
                        mode,
                    ))
                    os.chmod(fn, mode)
                yield fn
            except OSError as e:
                log.debug("Failed to chown %s: %r" % (fn, e))


class SystemRelease(File):
    """Informations about the OS based on /etc/system-release-cpe

    Use openscap_api.cpe.name_new(str) from openscap-python for an official
    way.
    """
    CPE_FILE = "/etc/system-release-cpe"

    VENDOR = None
    PRODUCT = None
    VERSION = None

    @property
    def uri(self):
        return self.contents.strip()

    def __str__(self):
        return "<CPE uri='%s' />" % self.uri

    def __init__(self, fn):
        self.filename = fn
        cpe_uri = self.contents
        cpe_parts = cpe_uri.split(":")
        if cpe_parts[0] != "cpe":
            raise RuntimeError("Can not parse CPE string in %s" %
                               self.CPE_FILE)
        self.VENDOR, self.PRODUCT, self.VERSION = cpe_parts[2:5]

    def is_supported_product(self):
        return self.PRODUCT in ["fedora", "centos", "enterprise_linux"]


class OSRelease(ShellVarFile):
    """Information about the OS based on /etc/os-release
    """
    NAME = fileMappedPropperty("NAME")
    VERSION = fileMappedPropperty("VERSION")
    PRETTY_NAME = fileMappedPropperty("PRETTY_NAME")
    ID = fileMappedPropperty("ID")
    VARIANT = fileMappedPropperty("VARIANT")
    VARIANT_ID = fileMappedPropperty("VARIANT_ID")

    def __init__(self, fn="/etc/os-release"):
        super(OSRelease, self).__init__(fn)


class BuildMetadata():
    """Store some metdata in the image

    >>> import tempfile
    >>> tmpdir = tempfile.mkdtemp()
    >>> BuildMetadata._meta_path = tmpdir

    >>> m = BuildMetadata()
    >>> m.set("nvr", "0.0.1")
    >>> m.get("nvr")
    '0.0.1'

    >>> m.keys()
    ['nvr']

    >>> m.items()
    [('nvr', '0.0.1')]
    """
    _meta_path = "/usr/share/imgbase/build/meta/"

    allowed_keys = ["nvr"]

    def __init__(self, root="/"):
        self._meta_path = root + self._meta_path
        if not os.path.exists(self._meta_path):
            os.makedirs(self._meta_path)

    def _metafile(self, key):
        assert key in self.allowed_keys
        return File(self._meta_path + "/" + key)

    def keys(self):
        return os.listdir(self._meta_path)

    def items(self):
        return [(k, self.get(k))
                for k in self.keys()]

    def set(self, key, value):
        self._metafile(key).write(value)

    def get(self, key):
        return self._metafile(key).contents

    def delete(self, key):
        self._metafile(key).remove()


# Based on: https://svn.blender.org/svnroot/bf-blender/trunk/blender/
# build_files/scons/tools/bcolors.py
class bcolors():
    HEADER = '\033[35m'
    OKBLUE = '\033[34m'
    OKGREEN = '\033[32m'
    WARNING = '\033[33m'
    FAIL = '\033[31m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

    @classmethod
    def warn(cls, txt):
        return cls.WARNING + txt + cls.ENDC

    @classmethod
    def fail(cls, txt):
        return cls.FAIL + cls.BOLD + txt + cls.ENDC

    @classmethod
    def ok(cls, txt):
        return cls.OKGREEN + txt + cls.ENDC

    @classmethod
    def bold(cls, txt):
        return cls.BOLD + txt + cls.ENDC


class bcolors256(bcolors):
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class ThreadRunner(threading.Thread):
    """Simple abstraction so we can run 'bare' methods inside threads
    and keep access to semantics for thread synchronization, which
    using pure thread.start_new_thread() will not do

    """

    def __init__(self, function, *args, **kwargs):
        self._function = function
        self._func_args = args
        self._func_kwargs = kwargs
        self.__exceptions = Queue()
        threading.Thread.__init__(self, name=self._function.__name__)

    def run(self):
        try:
            self._function(*self._func_args, **self._func_kwargs)
        except Exception:
            self.__exceptions.put(sys.exc_info())
        self.__exceptions.put(None)

    def _wait_exc(self):
        return self.__exceptions.get()

    def join_with_exceptions(self):
        exc = self._wait_exc()

        if exc is None:
            return
        else:
            log.debug(''.join(traceback.format_exception(*exc)))
            raise exc[1]


def thread_group_handler(threads, exc=None):
    threaded = not os.getenv("IMGBASED_DISABLE_THREADS")
    [getattr(t, "start" if threaded else "run")() for t in threads]

    for t in threads:
        try:
            t.join_with_exceptions()
        except Exception:
            log.debug(traceback.format_exc())
            sys.exit(1)

# vim: sw=4 et sts=4

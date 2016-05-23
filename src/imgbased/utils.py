#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# imgbase
#
# Copyright (C) 2014  Red Hat, Inc.
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

import functools
import subprocess
import os
import logging
import re
import glob
import shlex
from contextlib import contextmanager


log = logging.getLogger(__package__)


class HumanReadableError(Exception):
    pass


def mkfs(device, fs="ext4"):
    return ExternalBinary().call(["mkfs.%s" % fs, device])


def augtool(*args):
    return ExternalBinary().augtool(list(args))


def copy_files(dst, srcs, *args):
    """Copy files

    Use the native copy command to also copy xattrs (for SELinux)
    """
    args = list(args) + srcs + [dst]
    cp = ExternalBinary().cp
    return cp(args)


def size_of_fstree(path):
    """Returns the size of the tree in bytes

    The size of sparse files is used, not the allocated amount.
    """
    du = ExternalBinary().du
    return int(du(["-sxb", path]).split()[0])


def grubby(*args, **kwargs):
    return ExternalBinary().grubby(list(args), **kwargs)


def grub2_set_default(key):
    ExternalBinary().grub2_set_default([key])


def findmnt(options, path):
    findmnt = ExternalBinary().findmnt
    try:
        return str(findmnt(["-n", "-o", options, path])).strip()
    except:
        return None


def find_mount_source(path):
    return findmnt("SOURCE", path)


def memoize(obj):
    cache = obj.cache = {}

    @functools.wraps(obj)
    def memoizer(*args, **kwargs):
        key = str(args) + str(kwargs)
        if key not in cache:
            cache[key] = obj(*args, **kwargs)
        return cache[key]
    return memoizer


def uuid():
    raw = File("/proc/sys/kernel/random/uuid").contents
    return raw.replace("-", "").strip()


def call(*args, **kwargs):
    kwargs["close_fds"] = True
    log.debug("Calling: %s %s" % (args, kwargs))
    return subprocess.check_output(*args, **kwargs).strip()


def format_to_pattern(fmt):
    """Take a format string and make a pattern from it
    https://docs.python.org/2/library/re.html#simulating-scanf

    >>> fmt = "Bar-%d"
    >>> pat = format_to_pattern(fmt)
    >>> pat
    'Bar-([-+]?\\\\d+)'

    >>> re.search(pat, "Bar-01").groups()
    ('01',)

    >>> fmt = "%s-%d"
    >>> pat = format_to_pattern(fmt)
    >>> pat
    '([\\\\S.]+)-([-+]?\\\\d+)'
    >>> re.search(pat, "org.Node-01").groups()
    ('org.Node', '01')
    """
    pat = fmt
    pat = pat.replace("%d", r"([-+]?\d+)")
    pat = pat.replace("%s", r"([\S.]+)")
    return pat


def remount(target, opts=""):
    ExternalBinary().call(["mount", "-oremount" + opts, target])


class MountPoint(object):
    source = None
    options = None
    target = None

    tmpdir = None

    def __init__(self, source, options=None, target=None):
        self.run = ExternalBinary()
        self.source = source
        self.options = options
        self.target = target

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
        cmd += [self.source, self.target]
        self.run.call(cmd)

    def umount(self):
        self.run.call(["umount", self.target])
        if self.tmpdir:
            self.run.call(["rmdir", self.tmpdir])

    def path(self, subpath):
        """Return the abs path to a path inside this mounted fs
        """
        return self.target + "/" + subpath


class mounted(object):
    mp = None

    def __init__(self, source, options=None, target=None):
        self.mp = MountPoint(source, options, target)

    def __enter__(self):
        self.mp.mount()
        return self.mp

    def __exit__(self, exc_type, exc_value, tb):
        self.mp.umount()
        return exc_type is None

    def path(self, subpath):
        return self.mp.path(subpath)


@contextmanager
def bindmounted(source, target):
    with mounted(source, target=target, options="bind") as mnt:
        yield mnt


def sorted_versions(versions, delim="."):
    return sorted(list(versions),
                  key=lambda s: list(map(int, s.split(delim))))


def kernel_versions_in_path(path):
    files = glob.glob("%s/vmlinu?-*" % path)
    versions = [os.path.basename(f).partition("-")[2] for f in files]
    return versions


def nsenter(args, root=None, wd="/"):
    _args = ["nsenter"]

    add_arg = lambda k, v: _args.append("--%s=%s" % (k, v))

    add_arg("root", root)
    add_arg("wd", wd)

    args = _args + list(args)

    return ExternalBinary().call(args)


def source_of_mountpoint(path):
    return ExternalBinary().findmnt(["--noheadings", "-o", "SOURCE", path])


class Filesystem():
    @staticmethod
    def get_type(path):
        cmd = ["blkid", "-o", "value", "-s", "TYPE", path]
        return subprocess.check_output(cmd).strip()

    @classmethod
    def from_device(cls, path):
        typ = cls.get_type(path)
        if typ == "ext4":
            cls = Ext4
        elif typ == "xfs":
            cls = XFS
        else:
            raise RuntimeError("Unknown filesystem %s on %s" % (typ, path))
        return cls(path)

    @classmethod
    def from_mountpoint(cls, path):
        source = source_of_mountpoint(path)
        assert source
        return cls.from_device(source)

    path = None

    def __init__(self, path):
        self.path = path

    @staticmethod
    def mkfs(path, debug=False):
        raise NotImplemented

    def randomize_uuid(self):
        raise NotImplemented


class Ext4(Filesystem):
    @staticmethod
    def mkfs(path, debug=False):
        cmd = ["mkfs.ext4", "-c", "-E", "discard", path]
        if not debug:
            cmd.append("-q")
        log.debug("Running: %s" % cmd)
        subprocess.check_call(cmd)

    def randomize_uuid(self):
        cmd = ["tune2fs", "-U", "random", self.path]
        log.debug("Running: %s" % cmd)
        subprocess.check_call(cmd)


class XFS(Filesystem):
    @staticmethod
    def mkfs(path, debug=False):
        cmd = ["mkfs.xfs", path]
        if not debug:
            cmd.append("-q")
        log.debug("Running: %s" % cmd)
        subprocess.check_call(cmd)

    def randomize_uuid(self):
        with mounted(self.path, options="nouuid"):
            # The fs needs to be mounted once to replay
            # eventual metadata
            pass
        cmd = ["xfs_admin", "-U", "generate", self.path]
        log.debug("Running: %s" % cmd)
        subprocess.check_call(cmd)


def findls(path):
    return ExternalBinary().find(["-ls"], cwd=path).splitlines(True)


class ExternalBinary(object):
    dry = False

    def call(self, *args, **kwargs):
        log.debug("Calling binary: %s %s" % (args, kwargs))
        stdout = bytes()
        if not self.dry:
            stdout = call(*args, **kwargs)
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

    def cp(self, args, **kwargs):
        return self.call(["cp"] + args, **kwargs)

    def augtool(self, args, **kwargs):
        return self.call(["augtool"] + args, **kwargs)

    def rpm(self, args, **kwargs):
        return self.call(["rpm"] + args, **kwargs)

    def grub2_set_default(self, args, **kwargs):
        return self.call(["grub2-set-default"] + args, **kwargs)

    def grubby(self, args, **kwargs):
        return self.call(["grubby"] + args, **kwargs)

    def systemctl(self, args, **kwargs):
        return self.call(["systemctl"] + args, **kwargs)


class LvmCLI():
    lvs = ExternalBinary().lvs
    vgs = ExternalBinary().vgs
    lvcreate = ExternalBinary().lvcreate
    lvchange = ExternalBinary().lvchange
    lvremove = ExternalBinary().lvremove
    vgcreate = ExternalBinary().vgcreate
    vgchange = ExternalBinary().vgchange


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

    def write(self, data, mode="w"):
        with open(self.filename, mode) as dst:
            dst.write(data)

    def writen(self, data, mode="w"):
        self.write(data + "\n")

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
            source, target, fs, options, _, _ = shlex.split(line)
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
        except:
            log.error("Failed to parse: %s" % line)
            raise
        return parsed

    def get(self, key, default):
        return self.parse().get(key, default)

    def set(self, key, val):
        self.sub(r"%s=.*" % key, "%s=%r" % (key, str(val)))


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

    def get_packages(self):
        raise NotImplementedError

    def get_files(self, pkgname):
        raise NotImplementedError


class RpmPackageDb(PackageDb):
    _rpm_cmd = lambda s, a: ExternalBinary().rpm(a)

    def _rpm(self, *args, **kwargs):
        if self.root:
            args += ("--root", self.root)
        return self._rpm_cmd(list(args)).splitlines(False)

    def get_packages(self, filter="", exclude=None):
        rpms = [p for p in self._rpm("-qa") if filter in p]

        return [p for p in rpms if exclude not in p] if exclude is not None \
            else rpms

    def get_files(self, pkgname):
        return self._rpm("-ql", pkgname)

    def get_nvr(self, pkgname):
        return self._rpm("-q", pkgname)


class systemctl():
    @staticmethod
    def _systemctl(*a):
        ExternalBinary().systemctl(list(a))

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
    def daemon_reload():
        systemctl._systemctl("daemon-reload")


class Rsync():
    existing = False
    exclude = None

    def __init__(self):
        self.exclude = []

    def _run(self, cmd):
        log.debug("Running: %s" % cmd)
        subprocess.check_call(cmd)

    def sync(self, sourcetree, dst):
        assert os.path.isdir(sourcetree)

        cmd = ["ionice", "rsync"]
        cmd += ["-pogAXtlHrx"]
        cmd += ["-Sc", "--no-i-r"]
        # cmd += ["--progress"]
        if self.existing:
            cmd += ["--existing"]
        if self.exclude:
            for pat in self.exclude:
                cmd += ["--exclude", pat]
        cmd += [sourcetree + "/", dst]

        self._run(cmd)


class IDMap():
    from_etc = None
    to_etc = None

    def __init__(self, from_etc, to_etc):
        self.from_etc = from_etc
        self.to_etc = to_etc

    def _parse_ids(self, fstab_data):
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
        [('bin', '1'), ('daemon', '2'), ('root', '0'), ('shutdown', '6'), \
('sync', '5')]
        """
        idmap = {}
        for line in fstab_data.splitlines():
            if not line:
                continue
            name, _, uid, gid = line.split(":")[:4]
            idmap[name] = uid
        return idmap

    def _create_idmap(self, from_idmap, to_idmap):
        """

        >>> from_map = {"root": "0", "bin": "1", "adm": "2"}
        >>> to_map = {"root": "0", "bin": "2", "adm": "3"}
        >>> IDMap(None, None)._create_idmap(from_map, to_map)
        [('1', '2'), ('2', '3')]
        """
        unknown_names = []
        xmap = []
        for fname, fid in from_idmap.items():
            if fname not in to_idmap:
                unknown_names.append(fname)
                continue
            tid = to_idmap[fname]
            if fid != tid:
                xmap.append((fid, tid))
        return sorted(xmap)

    def _create_idmaps(self, from_uids, from_gids, to_uids, to_gids):
        """

        >>> from_uids = {"root": "0", "bin": "1", "adm": "0"}
        >>> to_uids   = {"root": "0", "bin": "2", "adm": "0"}

        >>> from_gids = {"root": "0", "bin": "1", "adm": "2"}
        >>> to_gids   = {"root": "0", "bin": "2", "adm": "3"}

        >>> IDMap(None, None)._create_idmaps(from_uids, from_gids,
        ... to_uids, to_gids)
        ([('1', '2')], [('1', '2'), ('2', '3')])
        """

        uidmap = self._create_idmap(from_uids, to_uids)
        gidmap = self._create_idmap(from_gids, to_gids)

        return (uidmap, gidmap)

    def get_drift(self):
        """Returns the uid and gid dirft from the old to the net etc
        """
        from_uids = self._parse_ids(File(self.from_etc + "/passwd").contents)
        from_gids = self._parse_ids(File(self.from_etc + "/group").contents)

        to_uids = self._parse_ids(File(self.to_etc + "/passwd").contents)
        to_gids = self._parse_ids(File(self.to_etc + "/group").contents)

        uidmap, gidmap = self._create_idmaps(from_uids, from_gids,
                                             to_uids, to_gids)

        return (uidmap, gidmap)

    def has_drift(self):
        """Returns True if the id mapping of a group or user has changed
        """
        return sum(len(m) for m in self.get_drift()) > 0

    def _map_id_change(self, paths, _fake_drift=None):
        """Translate all uids/gids in path

        Imagine tehse paths with the owners:

        >>> paths = [("/foo", 11, 2),
        ...          ("/bar", 1, 22)]

        And a drift, weher uid 1 changed to 11, and gid 2 changed to 22:

        >>> drift = ([(1, 11)], [(2, 22)])

        Then IDMap will change the ids in the given path to the old ids.
        This ensures, that the owner does logically not change.

        >>> m = IDMap(None, None)
        >>> changes = m._map_id_change(paths, drift)
        >>> list(changes)
        [('/foo', (-1, 22)), ('/bar', (11, -1))]
        """

        drift = _fake_drift or self.get_drift()
        assert drift

        uidmap, gidmap = map(dict, drift)
        rev_uidmap = dict(map(reversed, uidmap.items()))
        rev_gidmap = dict(map(reversed, gidmap.items()))

        assert len(uidmap) == len(rev_uidmap)
        assert len(gidmap) == len(rev_gidmap)

        for (fn, uid, gid) in paths:
            new_ids = (uidmap.get(uid, -1),
                       gidmap.get(gid, -1))
            yield (fn, new_ids)

    def fix_drift(self, path):
        """This function will walk a tree and adjust all UID/GIDs which drifted
        """
        def paths_w_ids():
            for (dirpath, dirnames, filenames) in os.walk(path):
                for fn in dirnames + filenames:
                    fullfn = dirpath + "/" + fn
                    if not os.path.exists(fullfn):
                        log.debug("File does not exist: %s" % fn)
                        continue
                    st = os.stat(fullfn)
                    uid = st.st_uid
                    gid = st.st_gid
                    yield (fullfn, uid, gid)

        for (fn, new_ids) in self._map_id_change(paths_w_ids()):
            if any(v != -1 for v in new_ids):
                if os.path.exists(fn):
                    log.debug("Chowning %r to %s" % (fn, new_ids))
                    os.chown(fn, *new_ids)
                    yield fn
                else:
                    log.debug("Can't chown, file does not exist: %s" % fn)


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
    >>> m.set("nvr", "nvr")
    >>> m.get("nvr")
    'nvr'
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

    def set(self, key, value):
        self._metafile(key).write(value)

    def get(self, key):
        return self._metafile(key).contents

    def delete(self, key):
        self._metafile(key).remove()

# vim: sw=4 et sts=4

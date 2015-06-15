
import functools
import subprocess
import os
import logging
import sh
import re
import glob
import shlex
from six.moves.urllib import request


log = logging.getLogger(__package__)


def copy_files(dst, srcs, *args):
    """Copy files

    Use the native copy command to also copy xattrs (for SELinux)
    """
    args = list(args) + srcs + [dst]
    return sh.cp(*args)


def size_of_fstree(path):
    """Returns the size of the tree in bytes

    The size of sparse files is used, not the allocated amount.
    """
    return int(sh.du("-sxb", path).split()[0])


def request_url(url):
    return request.urlopen(url).read().decode()


def find_mount_source(path):
    try:
        return str(sh.findmnt("-n", "-oSOURCE", path)).strip()
    except:
        return None


def memoize(obj):
    cache = obj.cache = {}

    @functools.wraps(obj)
    def memoizer(*args, **kwargs):
        key = str(args) + str(kwargs)
        if key not in cache:
            cache[key] = obj(*args, **kwargs)
        return cache[key]
    return memoizer


def call(*args, **kwargs):
    kwargs["close_fds"] = True
    log.debug("Calling: %s %s" % (args, kwargs))
    return subprocess.check_output(*args, **kwargs).strip()


def chroot(target_root):
    if target_root and target_root != '/':
        os.chroot(target_root)
        os.chdir("/")


def format_to_pattern(fmt):
    """Take a format string and make a pattern from it
    https://docs.python.org/2/library/re.html#simulating-scanf

    >>> fmt = "Bar-%d"
    >>> pat = format_to_pattern(fmt)
    >>> pat
    'Bar-([-+]?\\\\d+)'

    >>> import re
    >>> re.search(pat, "Bar-01").groups()
    ('01',)
    """
    pat = fmt
    pat = pat.replace("%d", r"([-+]?\d+)")
    pat = pat.replace("%s", r"(\S+)")
    return pat


class mounted(object):
    source = None
    options = None
    _target = None

    run = None
    tmpdir = None

    @property
    def target(self):
        return self._target or self.tmpdir

    def __init__(self, source, options=None, target=None):
        self.run = ExternalBinary()
        self.source = source
        self.options = options
        self._target = target

    def __enter__(self):
        options = "-o%s" % self.options if self.options else None
        self.tmpdir = self._target or \
            self.run.call(["mktemp", "-d", "--tmpdir", "mnt.XXXXX"])

        if not os.path.exists(self.tmpdir):
            self.run.call(["mkdir", "-p", self.tmpdir])

        cmd = ["mount"]
        if options:
            cmd.append(options)
        cmd += [self.source, self.tmpdir]
        self.run.call(cmd)

        return self

    def __exit__(self, exc_type, exc_value, tb):
        self.run.call(["umount", self.target])
        if not self._target:
            self.run.call(["rmdir", self.tmpdir])
        return exc_type is None


def sorted_versions(versions, delim="."):
    return sorted(list(versions),
                  key=lambda s: list(map(int, s.split(delim))))


def kernel_versions_in_path(path):
    files = glob.glob("%s/vmlinu?-*" % path)
    versions = [os.path.basename(f).split("-",1 ).pop() for f in files]
    return versions


class ExternalBinary(object):
    dry = False

    def call(self, *args, **kwargs):
        log.debug("Calling binary: %s %s" % (args, kwargs))
        stdout = bytes()
        if not self.dry:
            stdout = call(*args, **kwargs)
            log.debug("Returned: %s" % stdout[0:1024])
        return stdout.decode().strip()

    def lvs(self, args, **kwargs):
        return self.call(["lvs"] + args, **kwargs)

    def vgs(self, args, **kwargs):
        return self.call(["vgs"] + args, **kwargs)

    def lvcreate(self, args, **kwargs):
        return self.call(["lvcreate"] + args, **kwargs)

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

    def tune2fs(self, args, **kwargs):
        return self.call(["tune2fs"] + args, **kwargs)


class File():
    filename = None

    @property
    def contents(self):
        return self.read()

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

        def __repr__(self):
            return "<Entry {self._index} {self.source} {self.target} />"\
                .format(self=self)

    def _read(self):
        return self.contents

    def parse(self):
        """
        >>> fstab = Fstab(None)
        >>> fstab._read = lambda: Fstab._testdata
        >>> fstab.parse()
        [<Entry 7 <root> / />, <Entry 8 <boot> /boot />, \
<Entry 9 <swap> swap />]
        """
        entries = []
        data = self._read()
        for idx, line in enumerate(data.splitlines()):
            if line.startswith("#") or line.strip() == "":
                continue
            source, target, fs, options, _, _ = shlex.split(line)
            entry = Fstab.Entry()
            entry._index = idx
            entry.source = source
            entry.target = target
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
        for idx, line in enumerate(data.strip().splitlines()):
            if idx != entry._index:
                newdata.append(line)
                continue
            tokens = shlex.split(line)
            tokens[0] = entry.source
            tokens[1] = entry.target
            newdata.append(" ".join(tokens))
        self.writen("\n".join(newdata))

    def by_source(self, source=None):
        """
        >>> Fstab._read = lambda x: Fstab._testdata
        >>> fstab = Fstab(None)
        >>> sorted(fstab.by_source().items())
        [('<boot>', <Entry 8 <boot> /boot />), \
('<root>', <Entry 7 <root> / />), \
('<swap>', <Entry 9 <swap> swap />)]
        >>> Fstab(None).by_source('<root>')
        <Entry 7 <root> / />
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
        [('/', <Entry 7 <root> / />), \
('/boot', <Entry 8 <boot> /boot />), \
('swap', <Entry 9 <swap> swap />)]
        >>> Fstab(None).by_target('/')
        <Entry 7 <root> / />
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
        ('A=1\\nB=b\\nAh=ah',)
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
        self.sub(r"%s=.*" % key, "%s=%s" % (key, str(val)))


class PackageDb():
    def get_files(self, pkgname):
        raise NotImplementedError


class RpmPackageDb(PackageDb):
    _rpm_cmd = sh.rpm

    def rpm(self, *args, **kwargs):
        return self._rpm_cmd(*args, **kwargs).splitlines(False)

    def get_files(self, pkgname):
        return self.rpm("-ql", pkgname)


class Rsync():
    _rsync_cmd = ["ionice", "rsync"]

    existing = False
    exclude = None

    def __init__(self):
        self.exclude = []

    def _run(self, cmd):
        log.debug("Running: %s" % cmd)
        subprocess.check_call(cmd)

    def sync(self, sourcetree, dst):
        assert os.path.isdir(sourcetree)
        assert os.path.isdir(dst)

        cmd = list(self._rsync_cmd)
        cmd += ["-pogAXtlHrDx"]
        cmd += ["-Sc", "--no-i-r"]
        cmd += ["--info=progress2"]
        if self.existing:
            cmd += ["--existing"]
        if self.exclude:
            for pat in self.exclude:
                cmd += ["--exclude", pat]
        cmd += [sourcetree + "/", dst]

        self._run(cmd)


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

# vim: sw=4 et sts=4

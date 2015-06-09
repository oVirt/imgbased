
import functools
import subprocess
import os
import logging
import sh
import shlex
from six.moves.urllib import request


log = logging.getLogger(__package__)


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
        self.run.call(["umount", self.source])
        if not self._target:
            self.run.call(["rmdir", self.tmpdir])


def sorted_versions(versions, delim="."):
    return sorted(list(versions),
                  key=lambda s: list(map(int, s.split(delim))))


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


class Fstab():
    _testdata = """/files/etc/fstab/1
/files/etc/fstab/1/spec = "/dev/mapper/fedora_pc192--168--2--115-root"
/files/etc/fstab/1/file = "/"
/files/etc/fstab/1/vfstype = "ext4"
/files/etc/fstab/1/opt[1] = "defaults"
/files/etc/fstab/1/opt[2] = "discard"
/files/etc/fstab/1/dump = "1"
/files/etc/fstab/1/passno = "1"
/files/etc/fstab/2
/files/etc/fstab/2/spec = "UUID=9ebd96d2-f42c-466b-96b6-a97e7690e78f"
/files/etc/fstab/2/file = "/boot"
/files/etc/fstab/2/vfstype = "ext4"
/files/etc/fstab/2/opt = "defaults"
/files/etc/fstab/2/dump = "1"
/files/etc/fstab/2/passno = "2"
/files/etc/fstab/3
/files/etc/fstab/3/spec = "/dev/mapper/fedora_pc192--168--2--115-swap"
/files/etc/fstab/3/file = "swap"
/files/etc/fstab/3/vfstype = "swap"
/files/etc/fstab/3/opt = "defaults"
/files/etc/fstab/3/dump = "0"
/files/etc/fstab/3/passno = "0"
"""

    _augtool = sh.augtool

    class Entry():
        _index = None
        source = None
        target = None

        def __repr__(self):
            return "<Entry {self._index} {self.source} {self.target} />"\
                .format(self=self)

    def parse(self):
        data = self._augtool("print", "/files/etc/fstab")
        return self._parse(data)

    def _parse(self, data=None):
        """Parse augtool output

        >>> Fstab()._parse(Fstab._testdata)
        [<Entry /files/etc/fstab/1 \
/dev/mapper/fedora_pc192--168--2--115-root / />, <Entry /files/etc/fstab/2 \
UUID=9ebd96d2-f42c-466b-96b6-a97e7690e78f /boot />, <Entry /files/etc/fstab/3 \
/dev/mapper/fedora_pc192--168--2--115-swap swap />]
        """
        entries = []
        augvals = {}
        for line in data.strip().splitlines():
            if "=" in line:
                augsubpath, value = line.split(" = ", 1)
                augpath, field = augsubpath.rsplit("/", 1)
                # [1:-1] remove teh always there quotes
                augvals.setdefault(augpath, {})[field] = value[1:-1]

        for path, vals in augvals.items():
            if "spec" not in vals:
                continue
            entry = Fstab.Entry()
            entry._index = path
            entry.source = vals["spec"]
            entry.target = vals["file"]
            entries.append(entry)

        return sorted(entries, key=lambda e: e._index)

    def update(self, entry):
        """

        >>> def printer(*args):
        ...     print(args)
        >>> fstab = Fstab()
        >>> fstab._augtool = printer
        >>> entries = fstab._parse(Fstab._testdata)
        >>> entry = entries[0]
        >>> entry.source = "foo"
        >>> fstab.update(entry)
        ('set', '/files/etc/fstab/1/spec', 'foo')
        ('set', '/files/etc/fstab/1/file', '/')
        >>> entry.target = "bar"
        >>> fstab.update(entry)
        ('set', '/files/etc/fstab/1/spec', 'foo')
        ('set', '/files/etc/fstab/1/file', 'bar')
        """
        for field, val in [("spec", entry.source), ("file", entry.target)]:
            augpath = "%s/%s" % (entry._index, field)
            self._augtool("set", augpath, val)

    def by_source(self, source=None):
        """
        >>> parsed = Fstab()._parse(Fstab._testdata)
        >>> Fstab.parse = lambda *args: parsed
        >>> sorted(Fstab().by_source().items())
        [('/dev/mapper/fedora_pc192--168--2--115-root', <Entry \
/files/etc/fstab/1 /dev/mapper/fedora_pc192--168--2--115-root / />), \
('/dev/mapper/fedora_pc192--168--2--115-swap', <Entry /files/etc/fstab/3 \
/dev/mapper/fedora_pc192--168--2--115-swap swap />), \
('UUID=9ebd96d2-f42c-466b-96b6-a97e7690e78f', <Entry /files/etc/fstab/2 \
UUID=9ebd96d2-f42c-466b-96b6-a97e7690e78f /boot />)]
        >>> Fstab().by_source('/dev/mapper/fedora_pc192--168--2--115-root')
        <Entry /files/etc/fstab/1 /dev/mapper/fedora_pc192--168--2--115-root \
/ />
        """
        sources = dict((e.source, e) for e in self.parse())
        if source:
            return sources[source]
        else:
            return sources

    def by_target(self, target=None):
        """
        >>> parsed = Fstab()._parse(Fstab._testdata)
        >>> Fstab.parse = lambda *args: parsed
        >>> sorted(Fstab().by_target().items())
        [('/', <Entry /files/etc/fstab/1 \
/dev/mapper/fedora_pc192--168--2--115-root / />), ('/boot', \
<Entry /files/etc/fstab/2 UUID=9ebd96d2-f42c-466b-96b6-a97e7690e78f \
/boot />), ('swap', <Entry /files/etc/fstab/3 \
/dev/mapper/fedora_pc192--168--2--115-swap swap />)]
        >>> Fstab().by_target('/')
        <Entry /files/etc/fstab/1 /dev/mapper/fedora_pc192--168--2--115-root \
/ />
        """
        targets = dict((e.target, e) for e in self.parse())
        if target:
            return targets[target]
        else:
            return targets


class ShellVarFile():
    filename = None

    def __init__(self, fn):
        self.filename = fn

    def parse(self, data=None):
        """Parse
        >>> testdata= 'VERSION_ID=22\\nPRETTY_NAME="Fedora 22 (Twenty Two)"\\n'
        >>> sorted(ShellVarFile(None).parse(testdata).items())
        [('PRETTY_NAME', 'Fedora 22 (Twenty Two)'), ('VERSION_ID', '22')]
        """
        if not data:
            with open(self.filename) as src:
                data = src.read()

        parsed = {}
        for keyval in shlex.split(data):
            key, val = keyval.split("=", 1)
            parsed[key] = val

        return parsed

    def _getitem__(self, key):
        return self.parsed()[key]


class File():
    @property
    def contents(self):
        return self.read()

    def __init__(self, fn):
        self.filename = fn

    def read(self):
        with open(self.filename) as src:
            return src.read()

    def exists(self):
        return os.path.exists(self.filename)

    def replace(self, pat, repl):
        self.write(self.contents.replace(pat, repl))

# vim: sw=4 et sts=4

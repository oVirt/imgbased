
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
    _testdata = """#Comment
/dev/mapper/fedora_root /                       ext4    defaults,discard        1 1
UUID=9ebd96d2-f42c-466b-96b6-a97e7690e78f /boot                   ext4    defaults        1 2
/dev/mapper/fedora_swap swap                    swap    defaults        0 0

"""
    filename = None

    class Entry():
        _index = None
        source = None
        target = None

        def __repr__(self):
            return "<Entry {self._index} {self.source} {self.target} />"\
                .format(self=self)

    def __init__(self, fn=None):
        self.filename = fn

    def _read(self):
        return File(self.filename).contents

    def parse(self):
        """
        >>> fstab = Fstab()
        >>> fstab._read = lambda: Fstab._testdata
        >>> fstab.parse()
        [<Entry 1 /dev/mapper/fedora_root / />,\
 <Entry 2 UUID=9ebd96d2-f42c-466b-96b6-a97e7690e78f /boot />,\
 <Entry 3 /dev/mapper/fedora_swap swap />]
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
        ...     print(args)
        >>> fstab = Fstab()
        >>> fstab._write = printer
        >>> entries = fstab.parse()
        >>> entry = entries[0]
        >>> entry.source = "foo"
        >>> fstab.update(entry)
        #Comment
	foo / ext4 defaults,discard 1 1
        UUID=9ebd96d2-f42c-466b-96b6-a97e7690e78f /boot                   ext4    defaults        1 2
        /dev/mapper/fedora_swap swap                    swap    defaults        0 0

        >>> entry.target = "bar"
        >>> fstab.update(entry)
        #Comment
        foo bar ext4 defaults,discard 1 1
        UUID=9ebd96d2-f42c-466b-96b6-a97e7690e78f /boot                   ext4    defaults        1 2
        /dev/mapper/fedora_swap swap                    swap    defaults        0 0
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
        self._write("\n".join(newdata))

    def _write(self, data):
        File(self.filename).write(data)

    def by_source(self, source=None):
        """
        >>> Fstab._read = lambda x: Fstab._testdata
        >>> fstab = Fstab()
        >>> sorted(fstab.by_source().items())
        [('/dev/mapper/fedora_root', \
<Entry 1 /dev/mapper/fedora_root / />), \
('/dev/mapper/fedora_swap', \
<Entry 3 /dev/mapper/fedora_swap swap />), \
('UUID=9ebd96d2-f42c-466b-96b6-a97e7690e78f', \
<Entry 2 UUID=9ebd96d2-f42c-466b-96b6-a97e7690e78f /boot />)]
        >>> Fstab().by_source('/dev/mapper/fedora_root')
        <Entry 1 /dev/mapper/fedora_root / />
        """
        sources = dict((e.source, e) for e in self.parse())
        if source:
            return sources[source]
        else:
            return sources

    def by_target(self, target=None):
        """
        >>> Fstab._read = lambda x: Fstab._testdata
        >>> fstab = Fstab()
        >>> sorted(fstab.by_target().items())
        [('/', <Entry 1 /dev/mapper/fedora_root / />), \
('/boot', <Entry 2 UUID=9ebd96d2-f42c-466b-96b6-a97e7690e78f /boot />), \
('swap', <Entry 3 /dev/mapper/fedora_swap swap />)]
        >>> Fstab().by_target('/')
        <Entry 1 /dev/mapper/fedora_root \
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
    filename = None

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

    def write(self, data, mode="w"):
        with open(self.filename, mode) as dst:
            dst.write(data)

# vim: sw=4 et sts=4

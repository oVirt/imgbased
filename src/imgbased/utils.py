
import functools
import subprocess
import os
import logging


def log():
    return logging.getLogger()


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
    log().debug("Calling: %s %s" % (args, kwargs))
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
        log().debug("Calling: %s %s" % (args, kwargs))
        stdout = ""
        if not self.dry:
            stdout = call(*args, **kwargs)
            log().debug("Returned: %s" % stdout[0:1024])
        return stdout.strip()

    def lvs(self, args, **kwargs):
        return self.call(["lvs"] + args, **kwargs)

    def vgs(self, args, **kwargs):
        return self.call(["vgs"] + args, **kwargs)

    def lvcreate(self, args, **kwargs):
        return self.call(["lvcreate"] + args, **kwargs)

    def vgcreate(self, args, **kwargs):
        return self.call(["vgcreate"] + args, **kwargs)

    def vgchange(self, args, **kwargs):
        return self.call(["vgchange"] + args, **kwargs)


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

# vim: sw=4 et sts=4

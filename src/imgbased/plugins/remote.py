
from ..utils import log
from ConfigParser import ConfigParser
from StringIO import StringIO
import shlex
import glob
import requests
from os import path
from pprint import pprint


def init(app):
    app.hooks.connect("pre-arg-parse", add_argparse)
    app.hooks.connect("post-arg-parse", check_argparse)


def add_argparse(app, parser, subparsers):
    """Add our argparser bit's to the overall parser
    It will be called when the app is launched
    """
    s = subparsers.add_parser("remote",
                              help="Fetch images from remote sources")

    s.add_argument("--nightly", action="store_true", help="Nightly image")
    s.add_argument("--stable", action="store_true", help="Stable image")

    # FIXME pull from jenkins based on config file


def check_argparse(app, args):
    """Check if we were asked to do something
    It will be called when the user selects a sub-command
    """
    log().debug("Operating on: %s" % app.imgbase)
    if args.command == "remote":
        raise NotImplemented()


def StringIOConfigParser(cfgstr):
    """A config parser which reads a string
    """
    p = ConfigParser()
    p.readfp(StringIO(cfgstr))

    for section in p.sections():
        yield (section, dict(p.items(section)))


class LocalRemotesConfiguration():
    """Datastructure to access localy configured remotes

    We configure remote repositories/locations locally,
    then we can use remote.pull(img) to add a remote image to our
    local VG.
    Just like git.

    >>> example = '''
    ... [general]
    ...
    ... [remote jenkins]
    ... url = http://jenkins.ovirt.org/
    ... '''

    >>> rs = LocalRemotesConfiguration()

    >>> rs._parse_config(example)
    {'jenkins': <Remote name=jenkins url=http://jenkins.ovirt.org/ \>}

    """
    CFGD_PATH = "/tmp/remotes.d"

    def list(self):
        """List all availabel remotes
        """
        remotes = {}
        for cfg in glob.glob(RemotesConfiguration.CFGD_PATH + "/*"):
            remotes.update(self.parse_config(cfg))
        return remotes

    def parse_config(self, filename):
        """Parse a single remote config file
        """
        with open(filename) as src:
            return self._parse_config(src.read())

    def _parse_config(self, cfgstr):
        """Parse a single config file

        >>> rs = LocalRemotesConfiguration()
        >>> rs._parse_config("")
        {}
        >>> rs._parse_config("[remote thing]\\nurl = bar")
        {'thing': <Remote name=thing url=bar \>}
        >>> rs._parse_config("[remote 'a thing']\\nurl = bar")
        {'a thing': <Remote name=a thing url=bar \>}
        """
        remotes = {}
        for section, items in StringIOConfigParser(cfgstr):
            if section.startswith("remote "):
                r = Remote()
                r.name = shlex.split(section)[1]
                r.url = items["url"]
                remotes[r.name] = r
        return remotes


class Remote(object):
    """Datastructure to operate on some remote repository with images

    Influenced by
    http://0pointer.net/blog/revisiting-how-we-put-together-linux-systems.html
    """
    name = None
    url = None

    _discoverer = None

    def __init__(self):
        self._discoverer = SimpleIndexImageDiscoverer(self)

    def list_images(self):
        return self._discoverer.list_images()

    def __repr__(self):
        return "<Remote name=%s url=%s \>" % \
            (self.name, self.url)


class RemoteImage():
    """Represents informations about a single remote image

    path: Is relative, a filename
    """
    reomte = None

    vendorid = None
    architecture = None
    version = None
    path = None

    def __init__(self, remote):
        self.remote = remote

    def __repr__(self):
        return "<Image name=%s vendorid=%s version=%s path=%s \>" % \
            (self.name, self.vendorid, self.version, self.path)

    def url(self):
        return self.remote.url + "/" + self.path

    def pull(self, dstpath):
        """Fetch and store a remote image

        dstpath: device or filename
        """
        url = self.url()
        req = requests.get(url)
        req.raise_for_status()
        with open(dstpath, "wb") as dst:
            for chunk in req.iter_content(1024):
                dst.write(chunk)
        #curl("--location", "--fail",
        #     "--output", imgbase


class SimpleIndexImageDiscoverer():
    """Remotely find images based on a simple index file

    >>> example = '''
    ... # A comment
    ... rootfs:<name>:<vendor>:<arch>:<version>.<suffix>
    ... '''

    >>> r = SimpleIndexImageDiscoverer(None)

    >>> r._list_images(example.split("\\n"))
    [<Image name=<name> vendorid=<vendor> version=<version> \
path=rootfs:<name>:<vendor>:<arch>:<version>.<suffix> \>]
    """
    indexfile = ".index"

    def __init__(self, remote):
        self.remote = remote

    def _imageinfo_from_name(self, filename):
        parts = filename.split(":")

        assert parts.pop(0) == "rootfs", "Only supporting rootfs images"

        info = RemoteImage(self.remote)
        info.path = filename
        info.name = parts.pop(0)
        info.vendorid = parts.pop(0)
        info.arch = parts.pop(0)
        info.version = parts.pop(0).split(".", 1)[0] # Strip an eventual suffix

        return info

    def _list_images(self, lines):
        filenames = []
        images = []
        for line in lines:
            if line and not line.startswith("#"):
                filenames.append(line)
        for filename in filenames:
            try:
                images.append(self._imageinfo_from_name(filename))
            except Exception as e:
                log().info("Failed to parse imagename '%s': %s" %
                           (filename, e))
        return images

    def list_images(self):
        src = requests.get(self.remote.url + "/" + self.indexfile).text
        lines = src.split("\n")
        return self._list_images(lines)

# vim: sw=4 et sts=4

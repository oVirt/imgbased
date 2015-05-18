
from ..utils import log
from ConfigParser import ConfigParser
from StringIO import StringIO
import shlex
import argparse
import sys
import requests
import re


def init(app):
    app.hooks.connect("pre-arg-parse", add_argparse)
    app.hooks.connect("post-arg-parse", check_argparse)


def add_argparse(app, parser, subparsers):
    """Add our argparser bit's to the overall parser
    It will be called when the app is launched
    """
    s = subparsers.add_parser("remote",
                              help="Fetch images from remote sources")

    su = s.add_subparsers(help="Comands to operate on remotes", dest="subcmd")

    su_add = su.add_parser("add", help="Add a remote")
    su_add.add_argument("NAME", type=str)
    su_add.add_argument("URL", type=str)

    su_remove = su.add_parser("remove", help="Remove a remote")
    su_remove.add_argument("NAME", type=str)

    su_list = su.add_parser("list", help="List availabel remote images")
    su_list.add_argument("NAME", type=str, nargs="?")

    su_fetch = su.add_parser("fetch", help="Retireve a remote image into "
                             "a dst")
    su_fetch.add_argument("NAME", type=str)
    su_fetch.add_argument("IMAGE", type=str)
    su_fetch.add_argument("DEST", nargs="?", type=argparse.FileType('r'),
                          default=sys.stdin,
                          help="File or stdin to use")

    su_pull = su.add_parser("pull", help="Pull a remote image and add it "
                            "to the layout")
    su_pull.add_argument("NAME", type=str)
    su_pull.add_argument("IMAGE", type=str)


def check_argparse(app, args):
    """Check if we were asked to do something
    It will be called when the user selects a sub-command
    """
    log().debug("Operating on: %s" % app.imgbase)
    if args.command != "remote":
        # Not us
        return

    remotes = LocalRemotesConfiguration()

    if args.subcmd == "add":
        remotes.add(args.NAME, args.URL)

    elif args.subcmd == "remove":
        remotes.remove(args.NAME)

    elif args.subcmd == "fetch":
        raise NotImplementedError()

    else: #if args.subcmd == "list":
        all_remotes = remotes.list()
        if args.NAME:
            print(all_remotes[args.NAME].list_images())
        else:
            for name, url in sorted(all_remotes.items()):
                print "%s: %s" % (name, url)


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
    >>> rs.cfgstr = example

    >>> rs.list()
    {'jenkins': <Remote name=jenkins url=http://jenkins.ovirt.org/ \>}
    """
    CFG_PATH = "/tmp/remotes_config"
    cfgstr = None

    def _parser(self):
        p = ConfigParser()
        if self.cfgstr is None:
            p.read(self.CFG_PATH)
        else:
            # Used for doctests
            p.readfp(StringIO(self.cfgstr))
        return p

    def _iter_sections(self):
        """A config parser which reads a string

        >>> example = '''
        ... [foo]
        ... a = 1
        ... [bar]
        ... b = 2
        ... '''

        >>> rs = LocalRemotesConfiguration()
        >>> rs.cfgstr = example
        >>> list(rs._iter_sections())
        [('foo', {'a': '1'}), ('bar', {'b': '2'})]
        """
        p = self._parser()
        for section in p.sections():
            yield (section, dict(p.items(section)))

    def list(self):
        """List all availabel remotes

        >>> example = '''
        ... [general]
        ...
        ... [remote jenkins]
        ... url = http://jenkins.ovirt.org/
        ... '''

        >>> rs = LocalRemotesConfiguration()
        >>> rs.cfgstr = example

        >>> rs.list()
        {'jenkins': <Remote name=jenkins url=http://jenkins.ovirt.org/ \>}

        >>> rs = LocalRemotesConfiguration()
        >>> rs.cfgstr = ""
        >>> rs.list()
        {}

        >>> rs.cfgstr = "[remote thing]\\nurl = bar"
        >>> rs.list()
        {'thing': <Remote name=thing url=bar \>}

        >>> rs.cfgstr = "[remote 'a thing']\\nurl = bar"
        >>> rs.list()
        {'a thing': <Remote name=a thing url=bar \>}
        """
        remotes = {}
        for section, items in self._iter_sections():
            if section.startswith("remote "):
                r = Remote()
                r.name = shlex.split(section)[1]
                r.url = items["url"]
                remotes[r.name] = r
        return remotes

    def add(self, name, url):
        p = self._parser()
        section = "remote %s" % name
        p.add_section(section)
        p.set(section, "url", url)
        self._save(p)

    def remove(self, name):
        p = self._parser()
        section = "remote %s" % name
        p.remove_section(section)
        self._save(p)

    def _save(self, p):
        with open(self.CFG_PATH, 'wb') as configfile:
            p.write(configfile)


class Remote(object):
    """Datastructure to operate on some remote repository with images

    Influenced by
    http://0pointer.net/blog/revisiting-how-we-put-together-linux-systems.html
    """
    name = None
    url = None

    _discoverer = None

    def __init__(self, name=None, url=None):
        self._discoverer = SimpleIndexImageDiscoverer(self)
        self.name = name
        self.url = url

    def list_images(self):
        return self._discoverer.list_images()

    def __repr__(self):
        return "<Remote name=%s url=%s \>" % \
            (self.name, self.url)


class RemoteImage():
    """Represents informations about a single remote image

    path: Is relative, a filename
    """
    remote = None

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
        """Retrieve the url to retrieve an image
        >>> remote = Remote("faraway", "http://far.away/")
        >>> img = RemoteImage(remote)
        >>> img.path = "relfile"
        >>> img.url()
        'http://far.away//relfile'

        >>> img.path = "http://foo.bar/"
        >>> img.url()
        'http://foo.bar/'

        >>> img.path = "file://foo/bar/"
        >>> img.url()
        'file://foo/bar/'

        """
        url = self.remote.url + "/" + self.path
        if re.search("(https?|file)://", self.path):
            url = self.path
        return url


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
        # curl("--location", "--fail",
        #      "--output", imgbase


class SimpleIndexImageDiscoverer():
    """Remotely find images based on a simple index file

    >>> example = '''
    ... # A comment
    ... rootfs:<name>:<vendor>:<arch>:<version>.<suffix>
    ... '''

    >>> r = SimpleIndexImageDiscoverer(None)

    >>> r._list_images(example.split("\\n")).values()
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
        # Strip an eventual suffix
        info.version = parts.pop(0).split(".", 1)[0]

        return info

    def _list_images(self, lines):
        filenames = []
        images = {}
        for line in lines:
            if line and not line.startswith("#"):
                filenames.append(line)
        for filename in filenames:
            try:
                images[filename] = self._imageinfo_from_name(filename)
            except Exception as e:
                log().info("Failed to parse imagename '%s': %s" %
                           (filename, e))
        return images

    def list_images(self):
        src = requests.get(self.remote.url + "/" + self.indexfile).text
        lines = src.split("\n")
        return self._list_images(lines)

# vim: sw=4 et sts=4

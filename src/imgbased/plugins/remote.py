
from ..utils import log
from ConfigParser import ConfigParser
from StringIO import StringIO
import shlex
import tempfile
import glob
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


class Remotes():
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

    >>> rs = Remotes()

    >>> rs._parse_config(example)
    {'jenkins': <Remote name=jenkins url=http://jenkins.ovirt.org/ \>}

    """
    CFGD_PATH = "/tmp/remotes.d"

    def list(self):
        """List all availabel remotes
        """
        remotes = {}
        for cfg in glob.glob(Remotes.CFGD_PATH + "/*"):
            remotes.update(self.parse_config(cfg))
        return remotes

    def parse_config(self, filename):
        """Parse a single remote config file
        """
        with open(filename) as src:
            return self._parse_config(src.read())

    def _parse_config(self, cfgstr):
        """Parse a single config file

        >>> rs = Remotes()
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

    Inspired by http://0pointer.net/blog/revisiting-how-we-put-together-linux-systems.html

    >>> example = '''
    ... [general]
    ... architecture = x86_64
    ... vendorid = org.ovirt.Node_UNSTABLE
    ...
    ... [image Node-20141010.0]
    ... version = 20141010.0
    ...
    ... [image Node-20141212.0]
    ... version = 20141212.0
    ... '''

    >>> r = Remote()
    >>> r.url = "http://example.com"

    >>> images = r._parse_imageinfo(example)

    >>> pprint(images)
    [<Image vendorid=org.ovirt.Node_UNSTABLE version=20141010.0 path=Node-20141010.0 \>,
     <Image vendorid=org.ovirt.Node_UNSTABLE version=20141212.0 path=Node-20141212.0 \>]

    >>> r._fetch_url(images[0])
    'http://example.com/Node-20141010.0'

    """
    name = None
    url = None

    IMAGEINFO_FILE = ".imageinfo"

    def _fetch_imageinfo(self):
        """Fetch the remote imageinfo file and return it's contents
        """
        with urllib2.urlopen(self.url + "/" + Remote.IMAGEINFO_FILE) as src:
            return src.read()

    def _parse_imageinfo(self, cfgstr):
        """Parse an imageinfo file and return the defined images

        >>> r = Remote()
        >>> r._parse_imageinfo("")
        []
        >>> r._parse_imageinfo("[image node-1.tar.xz]\\nversion=1.0")
        [<Image vendorid=None version=1.0 path=node-1.tar.xz \>]
        >>> r._parse_imageinfo("[image node-2.tar.xz]\\nversion=2.0")
        [<Image vendorid=None version=2.0 path=node-2.tar.xz \>]
        """
        images = []
        vendorid = arch = None
        for section, items in StringIOConfigParser(cfgstr):
            if section == "general":
                vendorid = items["vendorid"]
                arch = items["architecture"]

            if section.startswith("image "):
                i = ImageInfo()
                i.path = shlex.split(section)[1]
                i.vendorid = vendorid
                i.architecture = arch
                i.version = items.get("version", None)
                images.append(i)
        return images

    def _fetch_url(self, imageinfo):
        """Return the URL to fetch the given image from
        """
        return self.url + "/" + imageinfo.path

    def __repr__(self):
        return "<Remote name=%s url=%s \>" % \
            (self.name, self.url)

    def list_images(self):
        """List all available images at this remote
        """
        cfgstr = self._fetch_imageinfo()
        return self._parse_imageinfo(cfgstr)

    def pull(self, imageinfo):
        """Fetch and store a remote image
        """
        # fixme add hash
        #with open("FIXME", "wb") as dst:
        #    with urllib2.urlopen(self.url + "/" + imageinfo.path) as src:
        #        dst.write(src.read(1024))
        print path
        #curl("--location", "--fail",
        #     "--output", imgbase


class ImageInfo():
    """Represents informations about a single remote image
    """
    vendorid = None
    architecture = None
    version = None
    path = None

    def __repr__(self):
        return "<Image vendorid=%s version=%s path=%s \>" % \
            (self.vendorid, self.version, self.path)


# vim: sw=4 et sts=4

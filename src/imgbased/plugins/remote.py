
from ..utils import log, sorted_versions, request_url, mounted
from six.moves.configparser import ConfigParser
from io import StringIO
import shlex
import argparse
import sys
import re
import os
import urllib
import hashlib
import tempfile
import subprocess
import glob


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

    su_list = su.add_parser("list", help="List availabel remotes")
    su_list.add_argument("-a", "--all", help="List all images",
                         action="store_true")

    su_streams = su.add_parser("streams",
                               help="List availabel streams in a remote")
    su_streams.add_argument("NAME", type=str)

    su_images = su.add_parser("images",
                              help="List availabel images in a remote")
    su_images.add_argument("NAME", type=str)

    su_images = su.add_parser("versions",
                              help="List availabel versions of a stream")
    su_images.add_argument("NAME", type=str)
    su_images.add_argument("STREAM", type=str)

    su_fetch = su.add_parser("fetch", help="Retireve a remote image into "
                             "a dst")
    su_fetch.add_argument("NAME", type=str)
    su_fetch.add_argument("IMAGE", type=str)
    su_fetch.add_argument("DEST", nargs="?", type=argparse.FileType('r'),
                          default=sys.stdin,
                          help="File or stdin to use")

    su_pull = su.add_parser("get", help="Get a remote image")
    su_pull.add_argument("NAME", type=str)
    su_pull.add_argument("IMAGE", type=str)
    su_pull.add_argument("-o", "--output",
                         help="Specify an external destination for the " +
                         "pulled image",
                         type=argparse.FileType('wb'))
    su_pull.add_argument("-O",
                         help="Pull the remote image into a local file " +
                         "named like the remote file.",
                         action="store_true")

    p = subparsers.add_parser("pull",
                              help="Pull remote images into local bases")
    p.add_argument("--set-upstream", help="Upstream: <remote>/<stream>")
    p.add_argument("--version", help="Pull a specific version")


def check_argparse(app, args):
    """Check if we were asked to do something
    It will be called when the user selects a sub-command
    """
    log().debug("Operating on: %s" % app.imgbase)

    remotecfg = LocalRemotesConfiguration()

    if args.command == "remote":
        check_argparse_remote(app, args, remotecfg)
    if args.command == "pull":
        check_argparse_pull(app, args, remotecfg)


def check_argparse_pull(app, args, remotecfg):
    remotes = remotecfg.list()
    if args.set_upstream:
        pool = app.imgbase._thinpool().lvm_name
        remote, stream = args.set_upstream.split("/")
        remotecfg.set(remote, "pull", "%s:%s/%s" % (pool, remote, stream))
    else:
        log().debug("Fetching new image")
        remote = "jenkins"
        pool, remotestream = remotecfg.get(remote, "pull").split(":")
        remotename, stream = remotestream.split("/")
        remote = remotes[remotename]
        log().debug("Available remote streams: %s" %
                    remote.list_streams())
        log().debug("Available versions for stream '%s': %s" %
                    (stream, remote.list_versions(stream)))
        image = remote.get_image(stream)
        if remote.mode == "liveimg":
            with tempfile.NamedTemporaryFile() as tmpfile:
                image.pull(tmpfile.name)
                from sh import cp
                import os
#                cp(tmpfile.name, "/var/tmp/" + os.path.basename(image.url()))
                with mounted(tmpfile.name) as squashfs:
                    print(squashfs)
                    liveimg = glob.glob(squashfs.target + "/*/*.img").pop()
                    print(liveimg)
                    with mounted(liveimg) as rootfs:
                        app.imgbase.add_base_with_tree(rootfs.target, "2048M")
        else:
            raise RuntimeError("Mode not implemented: %s" % mode)

def check_argparse_remote(app, args, remotecfg):
    remotes = remotecfg.list()
    if args.subcmd == "add":
        remotecfg.add(args.NAME, args.URL)

    elif args.subcmd == "remove":
        remotecfg.remove(args.NAME)

    elif args.subcmd == "get":
        log().info("Pulling image '%s' from remote '%s':" %
                   (args.IMAGE, args.NAME))
        image = remotes[args.NAME].list_images()[args.IMAGE]
        if output:
            dst = output.name
        elif O:
            dst = os.path.basename(image.path)
        else:
            raise RuntimeError("Please pass -O or --output")
        log().info("Pulling image '%s' into '%s'" % (image.path, dst))
        image.pull(dst)

    elif args.subcmd == "streams":
        log().info("Available streams in '%s':" % args.NAME)
        streams = remotes[args.NAME].list_streams()
        for stream in streams:
            print(stream)

    elif args.subcmd == "images":
        log().info("Available images in remote '%s':" % args.NAME)
        images = remotes[args.NAME].list_images()
        for image in images.values():
            print(image.shorthash(),
                  image.vendorid,
                  image.name,
                  image.version)

    elif args.subcmd == "versions":
        print(remotes[args.NAME].list_versions(args.STREAM))

    elif args.subcmd == "list":
        for name, url in sorted(remotes.items()):
            print("%s: %s" % (name, url))


class LocalRemotesConfiguration():
    """Datastructure to access localy configured remotes

    We configure remote repositories/locations locally,
    then we can use remote.pull(img) to add a remote image to our
    local VG.
    Just like git.

    >>> example = '''
    ... [core]
    ...
    ... [remote jenkins]
    ... url = http://jenkins.ovirt.org/
    ... '''

    >>> rs = LocalRemotesConfiguration()
    >>> rs.cfgstr = example

    >>> rs.list()
    {'jenkins': <Remote name=jenkins url=http://jenkins.ovirt.org/ \>}
    """
    USER_CFG_DIR = os.path.expandvars("$HOME/.config/imgbase/")
    USER_CFG_FILE = USER_CFG_DIR + "/config"
    cfgstr = None

    def _parser(self):
        p = ConfigParser()
        if self.cfgstr is None:
            p.read(self.USER_CFG_FILE)
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
        section = "remote %s" % shlex.quote(name)
        p.add_section(section)
        p.set(section, "url", url)
        self._save(p)

    def set(self, name, key, val):
        p = self._parser()
        section = "remote %s" % shlex.quote(name)
        p.set(section, key, val)
        self._save(p)

    def get(self, name, key):
        p = self._parser()
        section = "remote %s" % shlex.quote(name)
        return p.get(section, key)

    def remove(self, name):
        p = self._parser()
        section = "remote %s" % shlex.quote(name)
        p.remove_section(section)
        self._save(p)

    def _save(self, p):
        try:
            os.makedirs(self.USER_CFG_DIR)
        except FileExistsError:
            log().debug("Config file dir already exists: %s" %
                        self.USER_CFG_DIR)
        with open(self.USER_CFG_FILE, 'wt') as configfile:
            print(p)
            p.write(configfile)
            log().debug("Wrote config file %s" % configfile)


class Remote(object):
    """Datastructure to operate on some remote repository with images

    Influenced by
    http://0pointer.net/blog/revisiting-how-we-put-together-linux-systems.html
    """
    name = None
    url = None

    _discoverer = None

    @property
    def _remote_configfile(self):
        return self.url + "/config"

    @property
    def config(self):
        cfg = request_url(self._remote_configfile)
        log().debug("Got remote config: %s", cfg)
        p = ConfigParser()
        p.readfp(StringIO(cfg))
        return p

    @property
    def mode(self):
        return self.config.get("core", "mode")

    def __init__(self, name=None, url=None):
        self._discoverer = SimpleIndexImageDiscoverer(self)
        self.name = name
        self.url = url

    def list_images(self):
        return self._discoverer.list_images()

    def list_streams(self):
        """List all streams in this remote

        >>> def fake_images():
        ...     images = {}
        ...     for t in [("org.example", "Client", "1"),
        ...               ("org.example", "Client", "2"),
        ...               ("org.example", "Server", "1"),
        ...               ("org.example", "Server", "1-1"),
        ...               ("org.example", "Server", "1-2"),
        ...               ("org.example", "Server", "1-12"),
        ...               ("org.example", "Server", "2-0")]:
        ...         i = RemoteImage(None)
        ...         i.vendorid, i.name, i.version = t
        ...         images[str(t)] = i
        ...     return images

        >>> r = Remote('foo', 'http://www.foo.com')
        >>> r.list_images = fake_images

        >>> r.list_streams()
        ['org.example.Client', 'org.example.Server']

        >>> r.list_versions("org.example.Server")
        ['1', '1-1', '1-2', '1-12', '2-0']
        """
        return sorted(set(i.stream() for i in self.list_images().values()))

    def list_versions(self, stream):
        """Get all versions of a stream in this remote
        """
        versions = (i.version for i in self.list_images().values()
                    if i.stream() == stream)
        return sorted_versions(versions, "-")

    def latest_version(self, stream):
        assert stream in self.list_streams()
        versions = self.list_versions(stream)
        log().debug("All versions: %s" % versions)
        return versions[-1]

    def get_image(self, stream, version=None):
        assert stream in self.list_streams()
        version = version or self.latest_version(stream)
        return [i for i in self.list_images().values()
                if i.version == version].pop()

    def __repr__(self):
        return "<Remote name=%s url=%s mode=%s />" % \
            (self.name, self.url, self.mode)


class RemoteImage():
    """Represents informations about a single remote image

    path: Is relative, a filename
    """
    remote = None

    vendorid = None
    architecture = None
    version = None
    path = None
    suffix = None

    @property
    def mode(self):
        return self.remote.mode

    def __init__(self, remote):
        self.remote = remote

    def __repr__(self):
        return "<Image name=%s vendorid=%s version=%s path=%s \>" % \
            (self.name, self.vendorid, self.version, self.path)

    def __str__(self):
        return "%s.%s = %s" % \
            (self.vendorid, self.name, self.version)

    def __hash__(self):
        return int(hashlib.sha1(self.path.encode("utf-8")).hexdigest(), 16)

    def shorthash(self):
        return ("{0:x}".format(hash(self)))[0:7]

    def stream(self):
        """Retrieve the stream of an image
        >>> img = RemoteImage(None)
        >>> img.vendorid = "org.example"
        >>> img.name = "Host"
        >>> img.stream()
        'org.example.Host'
        """

        return "%s.%s" % (self.vendorid, self.name)

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
        if re.search("(https?|file)://", self.path):
            url = self.path
        else:
            url = self.remote.url + "/" + self.path
        return url

    def pull(self, dstpath):
        """Fetch and store a remote image

        dstpath: device or filename

        >>> src = "/tmp/src"
        >>> dst = "/tmp/dst"

        >>> with open(src, "w") as f:
        ...     f.write("Hey!")
        4

        >>> img = RemoteImage(None)
        >>> img.path = "file://%s" % src
        >>> img.url()
        'file:///tmp/src'

        >>> img.pull(dst)

        >>> with open(dst) as f:
        ...     f.read()
        'Hey!'
        """
        url = self.url()
        log().info("Fetching image from url '%s'" % url)
        subprocess.check_call(["curl", "--location",
                               "--fail", "--output",
                               dstpath, url])


class ImageDiscoverer():
    remote = None

    def __init__(self, remote):
        self.remote = remote

    def _imageinfo_from_name(self, path):
        """Parse some format:

        >>> fmt = "rootfs:<name>:<vendor>:<arch>:<version>.<suffix.es>"
        >>> ImageDiscoverer(None)._imageinfo_from_name(fmt)
        <Image name=<name> vendorid=<vendor> version=<version> \
path=rootfs:<name>:<vendor>:<arch>:<version>.<suffix.es> \>
        """
        filename = os.path.basename(path)

        # We need to unquote the filename, because it can be an ULR with
        # escaped chars (like the :)
        parts = urllib.parse.unquote(filename).split(":")

        assert parts.pop(0) == "rootfs", "Only supporting rootfs images"

        info = RemoteImage(self.remote)
        info.path = path
        info.name = parts.pop(0)
        info.vendorid = parts.pop(0)
        info.arch = parts.pop(0)
        # Strip an eventual suffix
        info.version, info.suffix = parts.pop(0).split(".", 1)

        return info

    def list_images(self):
        raise NotImplemented()


class SimpleIndexImageDiscoverer(ImageDiscoverer):
    """Remotely find images based on a simple index file

    >>> example = '''
    ... # A comment
    ... rootfs:<name>:<vendor>:<arch>:<version>.<suffix>
    ... rootfs:NodeAppliance:org.ovirt.node:x86_64:2.20420102.0.squashfs
    ... http://example.com/rootfs:Some:org.example:x86_64:2.0.squashfs
    ... '''

    >>> r = SimpleIndexImageDiscoverer(None)

    >>> images = r._list_images(example.splitlines())
    >>> sorted([i.name for i in images.values()])
    ['<name>', 'NodeAppliance', 'Some']
    """

    @property
    def _remote_indexfile(self):
        return self.remote.url + "/index"

    def _list_images(self, lines):
        filenames = []
        images = {}
        for line in lines:
            if line and not line.startswith("#"):
                filenames.append(line)
        for filename in filenames:
            try:
                img = self._imageinfo_from_name(filename)
                images[img.shorthash()] = img
            except AssertionError as e:
                log().info("Failed to parse imagename '%s': %s" %
                           (filename, e))
        log().debug("Found images: %s" % images)
        return images

    def list_images(self):
        log().debug("Requesting index from: %s" % self._remote_indexfile)
        src = request_url(self._remote_indexfile).strip()
        lines = src.splitlines()
        return self._list_images(lines)

# vim: sw=4 et sts=4

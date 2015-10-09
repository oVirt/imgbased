
from ..utils import sorted_versions, request_url, mounted, \
    size_of_fstree
from ..local import Configuration
from six.moves import configparser
from io import StringIO
import argparse
import sys
import re
import os
import hashlib
import tempfile
import subprocess
import glob
import logging
try:
    from urllib.request import unquote
except ImportError:
    from urllib import unquote


log = logging.getLogger(__package__)


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
    su_images.add_argument("IMAGE", type=str, nargs="?",
                           help="Get this image")
    su_images.add_argument("-o", "--output",
                           help="Write the image to <file> instead of stdout",
                           type=argparse.FileType('wb'))
    su_images.add_argument("-O",
                           help="Write image to a local file named like" +
                                " the remote image we get.",
                           action="store_true")

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

    u = subparsers.add_parser("update",
                              help="Pull updates into the local pool")
    u.add_argument("--set-upstream", help="Set the upstream for updates "
                   "<remote>:<stream>", metavar="REMOTE:STREAM")
    u.add_argument("--check", action="store_true",
                   help="Check for available updates")
    u.add_argument("--version", help="Pull a specific version")
    u.add_argument("--fetch", help="Fetch the image and add a base, " +
                                   "but don't add a boot layer.")


def check_argparse(app, args):
    """Check if we were asked to do something
    It will be called when the user selects a sub-command
    """
    log.debug("Operating on: %s" % app.imgbase)

    remotecfg = RemotesConfiguration()

    if args.command == "remote":
        check_argparse_remote(app, args, remotecfg)
    if args.command == "update":
        check_argparse_update(app, args, remotecfg)


def check_argparse_update(app, args, remotecfg):
    remotes = remotecfg.remotes()
    pool = app.imgbase._thinpool().lvm_name
    if args.set_upstream:
        remote, sep, stream = args.set_upstream.partition(":")
        remotecfg.pool_upstream(pool, remote, stream)
    else:
        log.debug("Fetching new image")
        remotename, stream = remotecfg.pool_upstream(pool)
        assert remotename and stream, "Please set an upstream for '%s'" % pool
        remote = remotes[remotename]
        log.debug("Available remote streams: %s" %
                  remote.list_streams())
        log.debug("Available versions for stream '%s': %s" %
                  (stream, remote.list_versions(stream)))
        version = remote.latest_version(stream)
        image = remote.get_image(stream, version)
        log.debug("Latest image available is: %s" % repr(image))
        local_bases = app.imgbase.naming.bases()
        log.debug("Local bases: %s" % local_bases)
        needs_update = image.nvr not in (b.nvr for b in local_bases)

        if needs_update:
            log.info("New update available: %s" % image)
        else:
            log.info("No update available (latest is %s)." % image)
            return

        if args.check:
            return

        new_base = None
        if remote.mode == "liveimg":
            new_base = LiveimgExtractor(app.imgbase).extract(image)
        else:
            raise RuntimeError("Mode not implemented: %s" %
                               remote.mode)
        if args.fetch:
            log.info("Image was fetched successfully")
        else:
            assert new_base
            app.imgbase.add_layer(new_base)
            log.info("Update was pulled successfully")


def check_argparse_remote(app, args, remotecfg):
    remotes = remotecfg.remotes()
    if args.subcmd == "add":
        remotecfg.add(args.NAME, args.URL)

    elif args.subcmd == "remove":
        remotecfg.remove(args.NAME)

    elif args.subcmd == "streams":
        log.info("Available streams in '%s':" % args.NAME)
        streams = remotes[args.NAME].list_streams()
        for stream in streams:
            print(stream)

    elif args.subcmd == "images":
        log.info("Available images in remote '%s':" % args.NAME)
        images = remotes[args.NAME].list_images()

        if args.IMAGE:
            log.info("Pulling image '%s' from remote '%s':" %
                     (args.IMAGE, args.NAME))
            image = remotes[args.NAME].list_images()[args.IMAGE]
            if args.output:
                dst = args.output.name
            elif args.O:
                dst = os.path.basename(image.path)
            else:
                raise RuntimeError("Please pass -O or --output")
            log.info("Pulling image '%s' into '%s'" % (image.path, dst))
            image.download(dst)
        else:
            for image in images.values():
                print(image.shorthash(),
                      image.vendorid,
                      image.version)

    elif args.subcmd == "versions":
        print(remotes[args.NAME].list_versions(args.STREAM))

    elif args.subcmd == "list":
        for name, url in sorted(remotes.items()):
            print("%s: %s" % (name, url))


class RemotesConfiguration():
    """Datastructure to access localy configured remotes

    We configure remote repositories/locations locally,
    then we can use remote.pull(img) to add a remote image to our
    local VG.
    Just like git.

    >>> example = u'''
    ... [core]
    ...
    ... [remote jenkins]
    ... url = http://jenkins.ovirt.org/
    ... '''

    >>> rs = RemotesConfiguration()
    >>> rs.localcfg.cfgstr = example

    >>> rs.remotes()
    {'jenkins': <Remote name=jenkins url=http://jenkins.ovirt.org/ \
mode=None />}
    """

    localcfg = None

    class RemoteSection(Configuration.Section):
        # FIXME move to plugin
        _type = "remote"
        name = None
        url = None

    def __init__(self):
        RS = RemotesConfiguration.RemoteSection
        self.localcfg = Configuration()
        self.localcfg.register_section(RS)

    def remotes(self):
        """List all availabel remotes

        >>> example = '''
        ... [remote jenkins]
        ... url = http://jenkins.ovirt.org/
        ... '''

        >>> rs = RemotesConfiguration()
        >>> rs.localcfg.cfgstr = example

        >>> rs.remotes()
        {'jenkins': <Remote name=jenkins url=http://jenkins.ovirt.org/ \
mode=None />}

        >>> rs = RemotesConfiguration()
        >>> rs.localcfg.cfgstr = u""
        >>> rs.remotes()
        {}

        >>> rs.localcfg.cfgstr = u"[remote thing]\\nurl = bar"
        >>> rs.remotes()
        {'thing': <Remote name=thing url=bar mode=None />}

        >>> rs.localcfg.cfgstr = u"[remote a thing]\\nurl = bar"
        >>> rs.remotes()
        {'a thing': <Remote name=a thing url=bar mode=None />}

        >>> rs.remote("a thing")
        <RemoteSection (remote) [('name', 'a thing'), ('url', 'bar')] />
        """
        RS = RemotesConfiguration.RemoteSection
        remotes = {}
        for section in self.localcfg.sections(RS):
            r = Remote()
            r.name = section.name
            r.url = section.url
            remotes[r.name] = r
        return remotes

    def remote(self, name):
        return self.localcfg.section(RemotesConfiguration.RemoteSection,
                                     name)

    def pool_upstream(self, pool, remote=None, stream=None):
        try:
            s = self.localcfg.pool(pool)
        except:
            s = self.localcfg.PoolSection()
            s.name = pool
        if remote and stream:
            s.pull = "%s:%s" % (remote, stream)
            self.localcfg.save(s)
        return s.pull.split(":", 1)

    def add(self, name, url):
        s = self.RemoteSection()
        s.name = name
        s.url = url
        self.localcfg.save(s)

    def remove(self, name):
        self.localcfg.remove(self.remote(name))


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
        log.debug("Got remote config: %s", cfg)
        p = configparser.ConfigParser()
        p.readfp(StringIO(cfg))
        return p

    @property
    def mode(self):
        try:
            return self.config.get("core", "mode")
        except:
            return None

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
        ...     for t in [("org.example.Client", "1"),
        ...               ("org.example.Client", "2"),
        ...               ("org.example.Server", "1"),
        ...               ("org.example.Server", "1-1"),
        ...               ("org.example.Server", "1-2"),
        ...               ("org.example.Server", "1-12"),
        ...               ("org.example.Server", "2-0")]:
        ...         i = RemoteImage(None)
        ...         i.vendorid, i.version = t
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
        log.debug("All versions: %s" % versions)
        return versions[-1]

    def get_image(self, stream, version):
        assert stream in self.list_streams()
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

    @property
    def nvr(self):
        return "%s-%s.0" % (self.vendorid, self.version)

    def __init__(self, remote):
        self.remote = remote

    def __repr__(self):
        return "<Image vendorid=%s version=%s path=%s />" % \
            (self.vendorid, self.version, self.path)

    def __str__(self):
        return "%s-%s" % \
            (self.vendorid, self.version)

    def __hash__(self):
        return hash(self.nvr)

    def shorthash(self):
        return hashlib.sha1(self.path.encode("utf-8")).hexdigest()[0:7]

    def stream(self):
        """Retrieve the stream of an image

        >>> img = RemoteImage(None)
        >>> img.vendorid = "org.example.Host"
        >>> img.stream()
        'org.example.Host'
        """
        return self.vendorid

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

    def download(self, dstpath):
        """Fetch and store a remote image

        dstpath: device or filename

        >>> src = "/tmp/src"
        >>> dst = "/tmp/dst"

        >>> with open(src, "w") as f:
        ...     _ = f.write("Hey!")

        >>> img = RemoteImage(None)
        >>> img.path = "file://%s" % src
        >>> img.url()
        'file:///tmp/src'

        >>> img.download(dst)

        >>> with open(dst) as f:
        ...     f.read()
        'Hey!'
        """
        url = self.url()
        log.info("Fetching image from url '%s'" % url)
        subprocess.check_call(["curl", "--location",
                               "--fail", "--output",
                               dstpath, url])


class ImageDiscoverer():
    remote = None

    def __init__(self, remote):
        self.remote = remote

    def _imageinfo_from_filename(self, path):
        """Parse some format:

        >>> fmt = "rootfs:<vendor>:<arch>:<version>.<suffix.es>"
        >>> ImageDiscoverer(None)._imageinfo_from_filename(fmt)
        <Image vendorid=<vendor> version=<version> \
path=rootfs:<vendor>:<arch>:<version>.<suffix.es> />
        """
        filename = os.path.basename(path)
        log.debug("Parsing filename: %s" % filename)

        # We need to unquote the filename, because it can be an ULR with
        # escaped chars (like the :)
        parts = unquote(filename).split(":")

        assert parts.pop(0) == "rootfs", "Only supporting rootfs images"

        info = RemoteImage(self.remote)
        info.path = path
        info.vendorid = parts.pop(0)
        info.arch = parts.pop(0)
        # Strip an eventual suffix
        info.version, sep, info.suffix = parts.pop(0).partition(".")

        return info

    def list_images(self):
        raise NotImplemented()


class SimpleIndexImageDiscoverer(ImageDiscoverer):
    """Remotely find images based on a simple index file

    >>> example = '''
    ... # A comment
    ... rootfs:<vendor>:<arch>:<version>.<suffix>
    ... rootfs:org.ovirt.node.Node:x86_64:2.20420102.0.squashfs
    ... http://example.com/rootfs:org.example.Some:x86_64:2.0.squashfs
    ... '''

    >>> r = SimpleIndexImageDiscoverer(None)

    >>> images = r._list_images(example.splitlines())
    >>> sorted([i.vendorid for i in images.values()])
    ['<vendor>', 'org.example.Some', 'org.ovirt.node.Node']
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
                img = self._imageinfo_from_filename(filename)
                images[img.shorthash()] = img
            except AssertionError as e:
                log.info("Failed to parse imagename '%s': %s" %
                         (filename, e))
        log.debug("Found images: %s" % images)
        return images

    def list_images(self):
        log.debug("Requesting index from: %s" % self._remote_indexfile)
        src = request_url(self._remote_indexfile).strip()
        lines = src.splitlines()
        return self._list_images(lines)


class LiveimgExtractor():
    imgbase = None
    can_pipe = False

    def __init__(self, imgbase):
        self.imgbase = imgbase

    def _recommend_size_for_tree(self, path, scale=2.0):
        scaled = size_of_fstree(path) * scale
        remainder = scaled % 512
        return int(scaled + (512 - remainder))

    def write(self, image):
        raise NotImplementedError

    def extract(self, image):
        new_base = None
        log.info("Extracting image '%s'" % image)
        with tempfile.NamedTemporaryFile() as tmpfile:
            image.download(tmpfile.name)
            with mounted(tmpfile.name) as squashfs:
                log.debug("Mounted squashfs")
                liveimg = glob.glob(squashfs.target + "/*/*.img").pop()
                log.debug("Found fsimage at '%s'" % liveimg)
                with mounted(liveimg) as rootfs:
                    size = self._recommend_size_for_tree(rootfs.target, 3.0)
                    log.debug("Recommeneded base size: %s" % size)
                    log.info("Starting base creation")
                    add_tree = self.imgbase.add_base_with_tree
                    new_base = add_tree(rootfs.target,
                                        "%sB" % size,
                                        name=image.vendorid,
                                        version=image.version,
                                        release="0")
                    log.info("Files extracted")
        log.debug("Extraction done")
        return new_base

# vim: sw=4 et sts=4:

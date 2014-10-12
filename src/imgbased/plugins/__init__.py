
from ..utils import log
import pkgutil

plugins = []


for importer, modname, ispkg in pkgutil.iter_modules(__path__):
    log().debug("Found submodule %s (is a package: %s)" % (modname, ispkg))
    module = __import__(str(__package__) + "." + modname, fromlist="dummy")
    plugins.append(module)


def _on_all_plugins(funcname, *args):
    for p in plugins:
        if hasattr(p, funcname):
            f = getattr(p, funcname)
            log().debug("Calling init on: %s" % f)
            f(*args)


def init(app):
    _on_all_plugins("init", app)

# vim: et sw=4 sts=4

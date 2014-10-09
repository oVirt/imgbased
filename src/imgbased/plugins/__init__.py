
import pkgutil

plugins = []

for importer, modname, ispkg in pkgutil.iter_modules(__path__):
    print "Found submodule %s (is a package: %s)" % (modname, ispkg)
    module = __import__(str(__package__) + "." + modname, fromlist="dummy")
    plugins.append(module)

def _on_all_plugins(funcname, *args):
    for p in plugins:
        if hasattr(p, funcname):
            getattr(p, funcname)(*args)

def init(imgbase, hooks):
   _on_all_plugins("init", imgbase, hooks)

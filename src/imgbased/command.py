import logging
import os
import subprocess

log = logging.getLogger(__package__)


def call(*args, **kwargs):
    kwargs["close_fds"] = True
    if "stderr" not in kwargs:
        kwargs["stderr"] = subprocess.STDOUT
    log.debug("Calling: %s %s" % (args, kwargs))
    try:
        return subprocess.check_output(*args, **kwargs).strip()
    except subprocess.CalledProcessError as e:
        log.debug("Exception! %s" % e.output)
        raise


def nsenter(arg, new_root=None, shell=False, environ=None):
    DEVNULL = open(os.devnull, "w")
    if new_root:
        if shell:
            arg = "nsenter --root={0} --wd={0} {1}".format(new_root, arg)
        else:
            arg = [
                "nsenter",
                "--root={}".format(new_root),
                "--wd={}".format(new_root),
            ] + arg
    environ = environ or os.environ
    log.debug("Executing: %s", arg)
    proc = subprocess.Popen(arg, stdout=subprocess.PIPE, env=environ,
                            stderr=DEVNULL, shell=shell).communicate()
    ret = proc[0]
    log.debug("Result: %s", repr(ret))
    return ret


def chroot(args, root):
    return call(["chroot", root] + args)

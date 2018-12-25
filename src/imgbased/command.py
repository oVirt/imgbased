import os
import subprocess
import logging

log = logging.getLogger(__package__)


# TODO: make this more generic and deprecate utils.call()
def just_do(arg, new_root=None, shell=False, environ=None):
    DEVNULL = open(os.devnull, "w")
    if new_root:
        if shell:
            arg = "nsenter --root=%s --wd=/ %s" % (new_root, arg)
        else:
            arg = ["nsenter", "--root=" + new_root, "--wd=/"] + arg
    environ = environ or os.environ
    log.debug("Executing: %s", arg)
    proc = subprocess.Popen(arg, stdout=subprocess.PIPE, env=environ,
                            stderr=DEVNULL, shell=shell).communicate()
    ret = proc[0]
    log.debug("Result: %s", repr(ret))
    return ret

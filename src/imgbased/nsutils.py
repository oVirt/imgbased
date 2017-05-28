import uuid
import subprocess
import logging

from .utils import ExternalBinary, SELinuxDomain

log = logging.getLogger(__package__)


class NSBinary(ExternalBinary):
    @staticmethod
    def call_wait_pattern(args, parse_func=None, search_func=None):
        proc = subprocess.Popen(args, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        output = []
        while proc.poll() is None:
            line = proc.stdout.readline().strip()
            pline = parse_func(line) if parse_func else line
            log.debug("line: [%s]", pline)
            output.append(pline)
            if search_func and search_func(pline):
                break
        return output

    @staticmethod
    def systemd_nspawn(args, **kwargs):
        return NSBinary.call_wait_pattern(["stdbuf", "-o", "0",
                                           "systemd-nspawn"] + args, **kwargs)

    def machinectl(self, args, **kwargs):
        return self.call(["machinectl"] + args, **kwargs)

    def nsenter(self, args, **kwargs):
        return self.call(["nsenter"] + args, **kwargs)


class SystemdNS(object):
    _machinectl = NSBinary().machinectl
    _nsenter = NSBinary().nsenter

    _machine = None

    def __init__(self, path, boot=False, network=False):
        self._path = path
        self._boot = boot
        self._network = network
        if boot:
            self._boot_container()

    def _boot_container(self):
        if self._machine:
            return
        machine = "imgbased_" + str(uuid.uuid4())
        log.debug("Spawning a new systemd namespace: %s", machine)
        opts = "-bnD" if self._network else "-bD"
        NSBinary.systemd_nspawn(["-M", machine, opts, self._path],
                                search_func=lambda x: x.startswith("Kernel"))
        self._machine = self._machinectl_show(machine)
        assert self._is_running()

    def _machinectl_show(self, machine, props=None):
        sprops = set(["Name", "State", "Leader"])
        sprops.update(props if props else [])
        args = [v for p in zip(["-p"]*len(sprops), sprops) for v in p]
        machines = self._machinectl(["list", "--no-legend"]).split()[::3]
        if machine in machines:
            output = self._machinectl(["show", machine] + args)
            return dict([x.split("=") for x in output.split("\n")])
        return None

    def _is_running(self):
        return self._machine and self._machine.get("State") == "running"

    def exec_in(self, args):
        # If we dont need to boot, it's similar to running a simple chroot
        if not self._boot:
            return NSBinary.systemd_nspawn(["-qD", self._path] + args)
        if not self._is_running():
            self._boot_container()
        return self._nsenter(["--target", self._machine["Leader"], "--mount",
                              "--uts", "--ipc", "--net", "--pid"] + args)

    def shutdown(self):
        if not self._is_running():
            log.debug("No machine is running")
            return
        log.debug("Shutting down %s", self._machine["Name"])
        with SELinuxDomain("systemd_machined_t"):
            self._machinectl(["poweroff", self._machine["Name"]])

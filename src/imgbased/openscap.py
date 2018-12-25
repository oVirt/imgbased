import os
import time
import logging
from systemd import journal
from six.moves.configparser import ConfigParser
from .utils import File, bindmounted
from .command import just_do


log = logging.getLogger(__package__)


SCAP_BASEDIR = "/var/lib/imgbased/openscap"
SCAP_REPORTSDIR = SCAP_BASEDIR + "/reports"
SCAP_REPORT_FMT = SCAP_REPORTSDIR + "/scap-report-%s.html"


class ScapProfileError(Exception):
    pass


class ScapDatastreamError(Exception):
    pass


class OSCAPConfig(object):
    _config_file = SCAP_BASEDIR + "/config"
    _section = "openscap"
    _profile = "profile"
    _datastream = "datastream"
    _configured = "configured"

    def __init__(self):
        self._cp = ConfigParser()
        self._cp.read(self._config_file)
        if not self._cp.has_section(self._section):
            self._cp.add_section(self._section)

    def _set_value(self, key, val):
        self._cp.set(self._section, key, val)
        self._save()

    def _get_value(self, key, default=None):
        if not self._cp.has_option(self._section, key):
            return default
        return self._cp.get(self._section, key)

    def _save(self):
        with open(self._config_file, "w") as f:
            self._cp.write(f)

    @property
    def profile(self):
        return self._get_value(self._profile)

    @profile.setter
    def profile(self, value):
        return self._set_value(self._profile, value)

    @property
    def datastream(self):
        return self._get_value(self._datastream)

    @datastream.setter
    def datastream(self, value):
        return self._set_value(self._datastream, value)

    @property
    def registered(self):
        return bool(self.profile and self.datastream)

    @property
    def configured(self):
        return self._get_value(self._configured)

    @configured.setter
    def configured(self, value):
        return self._set_value(self._configured, value)


class OSCAPScanner(object):
    def __init__(self):
        if not os.path.exists(SCAP_REPORTSDIR):
            os.makedirs(SCAP_REPORTSDIR, mode=0o550)
        self._config = OSCAPConfig()

    def process(self, path):
        if self._config.registered:
            self.scan(remediate=True, path=path)
        else:
            self.configure()

    def register(self, datastream, profile):
        log.info("Registering profile %s from %s", profile, datastream)
        if profile not in self.profiles(datastream):
            log.error("Profile %s not found", profile)
            return
        self._config.datastream = os.path.realpath(datastream)
        self._config.profile = profile

    def unregister(self, profile):
        if profile == self._config.profile:
            log.info("Unregistering profile %s", profile)
            self._config.profile = ""
        else:
            log.warn("Profile [%s] is not registered, skipping", profile)

    def scan(self, remediate=False, path="/"):
        log.debug("Running OSCAP scan on %s, (remediate=%s)", path, remediate)
        if not self._config.registered:
            log.warn("Security profile not registered, skipping")
            return
        report = SCAP_REPORT_FMT % time.strftime("%Y%m%d%H%M%S")
        args = ["chroot", path, "oscap", "xccdf", "eval",
                "--profile", self.profile, "--report", report]
        if remediate:
            args.append("--remediate")
        args.append(self._config.datastream)
        with bindmounted("/proc", path + "/proc"):
            with bindmounted("/var", path + "/var", rbind=True):
                just_do(args)
        log.info("Report available at %s", report)

    def profiles(self, datastream=None):
        if not datastream:
            datastream = self._config.datastream
        if not datastream or not File(datastream).exists():
            raise ScapDatastreamError("Datastream not found: %s" % datastream)
        stdout = just_do(["oscap", "info", "--profiles", datastream])
        profiles = dict([x.split(":") for x in stdout.splitlines()])
        log.debug("Collected OSCAP profiles: %s", profiles)
        return profiles

    @property
    def profile(self):
        if not self._config.registered:
            raise ScapProfileError("SCAP profile not registered")
        return self._config.profile

    def configure(self):
        if self._config.configured:
            log.debug("SCAP was already auto-configured, skipping")
            return
        self._config.configured = "1"
        j = journal.Reader()
        j.this_boot()
        j.add_match(SYSLOG_IDENTIFIER="oscap")
        msgs = [x for x in j if x["MESSAGE"].startswith("Evaluation started")]
        if not msgs:
            log.info("No SCAP evaluation found, skipping")
            return
        ds, profile = [x[:-1] for x in msgs[0]["MESSAGE"].split()[3::2]]
        self.register(ds, profile)

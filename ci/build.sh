#!/usr/bin/bash

set -ex

export PATH=$PATH:/sbin:/usr/sbin
export TMPDIR=/var/tmp/

log() { echo -e "\n\n$@\n\n" ; }
include_ks() { cat $@ >> data/images/kickstarts/rootfs.ks ; }

log "Preparing the sources"
./autogen.sh
./configure

make clean clean-build

make -C data/images/ kickstarts/rootfs.ks

${WITH_VDSM:-false} && include_ks data/images/kickstarts/3rd-party/ovirt.ks
${WITH_GLUSTER:-false} && include_ks data/images/kickstarts/3rd-party/gluster.ks
${WITH_COCKPIT:-true} && include_ks data/images/kickstarts/3rd-party/cockpit.ks

log "Launching the build"
make image-build

log "Generate manifest"
guestfish -ia rootfs.qcow2 sh 'rpm -qa --qf "%{sourcerpm}\n" | sort -u' > manifest-srpm

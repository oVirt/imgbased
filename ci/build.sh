#!/usr/bin/bash

set -ex

export PATH=$PATH:/sbin:/usr/sbin
export TMPDIR=/var/tmp/

include_ks() { cat $@ >> rootfs.ks ; }

./autogen.sh
./configure

make clean rootfs.ks

${WITH_VDSM:-false} && include_ks data/kickstarts/3rd-party/ovirt.ks
${WITH_GLUSTER:-false} && include_ks data/kickstarts/3rd-party/gluster.ks
${WITH_COCKPIT:-true} && include_ks data/kickstarts/3rd-party/cockpit.ks

make image-build

guestfish -ia rootfs.qcow2 sh 'rpm -qa | sort -u' > manifest-rpm

#!/usr/bin/bash

set -ex

export PATH=$PATH:/sbin:/usr/sbin
export TMPDIR=/var/tmp/

include_ks() { cat data/kickstarts/payload/$@ >> rootfs.ks ; }

./autogen.sh
./configure

make clean rootfs.ks

${WITH_VDSM:-false} && include_ks ovirt.ks
${WITH_GLUSTER:-false} && include_ks gluster.ks
${WITH_COCKPIT:-true} && include_ks cockpit.ks
${WITH_DOCKER:-docker} && include_ks docker.ks

make image-build rootfs-manifest-rpm

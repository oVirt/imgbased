#!/usr/bin/bash

set -ex

export PATH=$PATH:/sbin:/usr/sbin
export TMPDIR=/var/tmp/

log() { echo -e "\n\n$@\n\n" ; }
include_ks() { cat $@ >> data/images/kickstarts/template/rootfs.ks ; }

log "Preparing the sources"
./autogen.sh
./configure

if ${WITH_VDSM:-false}
then
  include_ks data/images/kickstarts/3rd-party/ovirt.ks
fi

if ${WITH_GLUSTER:-false}
then
  include_ks data/images/kickstarts/3rd-party/gluster.ks
fi

log "Launching the build"
make image-build

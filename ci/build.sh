#!/usr/bin/bash

set -ex

export PATH=$PATH:/sbin:/usr/sbin
export TMPDIR=/var/tmp/
export http_proxy=$PROXY

log() { echo -e "\n\n$@\n\n" ; }

log "Preparing the sources"
./autogen.sh
./configure

if ${WITH_VDSM:-false}
then
  log "Including vdsm from the oVirt repositories"
  cat <<EOF >> data/images/kickstarts/template/rootfs.ks

%post
yum install -y http://resources.ovirt.org/pub/yum-repo/ovirt-release35.rpm
yum install -y vdsm
%end
EOF
fi

log "Launching the build"
make image-build

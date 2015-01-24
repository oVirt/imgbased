#!/usr/bin/bash

set -ex

export PATH=$PATH:/sbin:/usr/sbin
export TMPDIR=/var/tmp/
export http_proxy=$PROXY

log() { echo -e "\n\n$@\n\n" ; }

./autogen.sh
./configure

if $WITH_VDSM;
then
  cat <<EOF >> data/images/kickstarts/template/rootfs.ks

%post
yum install -y http://resources.ovirt.org/pub/yum-repo/ovirt-release35.rpm
yum install -y vdsm
%end
EOF
fi

log "Launching the build"
# 10.0.2.2 -- because that is the host ip inside the qemu container
make image-build PROXY=$PROXY

#!/usr/bin/bash

set -ex

export PATH=$PATH:/sbin:/usr/sbin
export TMPDIR=/var/tmp/

log() { echo -e "\n\n$@\n\n" ; }

log "Preparing the sources"
./autogen.sh
./configure

if ${WITH_VDSM:-false}
then
  log "Including vdsm from the oVirt repositories"
  cat <<EOF >> data/images/kickstarts/template/rootfs.ks

# Adding vdsm
%pre
yum install -y http://resources.ovirt.org/pub/yum-repo/ovirt-release35.rpm
%end
%packages
vdsm
%end
EOF
fi

if ${WITH_GLUSTER:-false}
then
  log "Including gluster from http://www.gluster.org"
  cat <<EOF >> data/images/kickstarts/template/rootfs.ks

# Adding gluster
%pre
yum-config-manager --add-repo="http://download.gluster.org/pub/gluster/glusterfs/LATEST/Fedora/glusterfs-fedora.repo"
%end
%packages
# Taken from http://www.gluster.org/documentation/quickstart/index.html
glusterfs
glusterfs-server
glusterfs-fuse
glusterfs-geo-replication
%end
EOF
fi

log "Launching the build"
make image-build

#!/usr/bin/bash

set -ex

export PATH=$PATH:/sbin/:/usr/sbin/
export TODAY=$(date +%Y%m%d)
export http_proxy=$PROXY

log() { echo -e "\n\n$@\n\n" ; }

log "Preparing the sources"
./autogen.sh
./configure

log "Performing installation"
make image-install

ln -v rootfs.squashfs.img $(make verrel).squashfs.img"

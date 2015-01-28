#!/usr/bin/bash

set -ex

export PATH=$PATH:/sbin/:/usr/sbin/

./autogen.sh
./configure

make image-install FORCE_REUSE_EXISTING_ROOTFS=1

ln -v rootfs.squashfs.img "$(make verrel).squashfs.img"

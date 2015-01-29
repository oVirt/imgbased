#!/usr/bin/bash

set -ex

export PATH=$PATH:/sbin/:/usr/sbin/

./autogen.sh
./configure

# Touch the rootfs.qcow2, to pretend that it is fresh
[ -f rootfs.qcow2 ] && touch rootfs.qcow2

make image-install

ln -v rootfs.squashfs.img "$(make verrel).squashfs.img"

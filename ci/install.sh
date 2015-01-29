#!/usr/bin/bash

set -ex

export PATH=$PATH:/sbin/:/usr/sbin/

./autogen.sh
./configure

make image-install

ln -v rootfs.squashfs.img "$(make verrel).squashfs.img"

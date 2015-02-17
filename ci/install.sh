#!/usr/bin/bash

set -ex

export PATH=$PATH:/sbin/:/usr/sbin/

./autogen.sh
./configure

git submodule update --init --recursive

[[ -n $SQUASHFS_URL ]] && make image-install SQUASHFS_URL=$SQUASHFS_URL || make image-install

IMG="$(make verrel).squashfs.img"
ln -v rootfs.squashfs.img $IMG

# Create an index file for imgbase remote
ls -1 > .index

# Create a kickstart for a specific location
mv -v installation.ks auto-installation.ks

# Create an inteactive kickstart for a specific location
sed -e "/^clearpart / d" auto-installation.ks > interactive-installation.ks

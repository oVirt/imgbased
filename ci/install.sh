#!/usr/bin/bash

set -ex

export PATH=$PATH:/sbin/:/usr/sbin/

./autogen.sh
./configure

# Touch the rootfs.qcow2, to pretend that it is fresh
[ -f rootfs.qcow2 ] && touch rootfs.qcow2

make image-install SQUASHFS_URL=$SQUASHFS_URL

IMG="$(make verrel).squashfs.img"
ln -v rootfs.squashfs.img $IMG

# Create an index file for imgbase remote
echo $IMG > .index

# Create a kickstart for a specific location
cp -v data/images/kickstarts/installation.ks auto-installation.ks

# Create an inteactive kickstart for a specific location
sed -e "/^clearpart / d" data/images/kickstarts/installation.ks > interactive-installation.ks

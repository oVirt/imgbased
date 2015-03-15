#!/usr/bin/bash

set -ex

export PATH=$PATH:/sbin/:/usr/sbin/

./autogen.sh
./configure

make rootfs.squashfs.img
[[ -n $SQUASHFS_URL ]] && make image-install SQUASHFS_URL=$SQUASHFS_URL || make image-install

IMG="$(make verrel).squashfs.img"
ln -v rootfs.squashfs.img $IMG

# Create an index file for imgbase remote
ls -1 > .index

# Create a kickstarts for auto and interactive installations
mv -v installation.ks auto-installation.ks
sed -e "/^clearpart / d" auto-installation.ks > interactive-installation.ks
sed -i "/http_proxy=/ d" *-installation.ks

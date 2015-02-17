#!/usr/bin/bash

set -ex

export PATH=$PATH:/sbin:/usr/sbin
export TMPDIR=/var/tmp/
log() { echo -e "\n\n$@\n\n" ; }

sudo yum -y install libguestfs-tools qemu-system-x86 asciidoc python-sh glusterfs gluster
git submodule update --init --recursive

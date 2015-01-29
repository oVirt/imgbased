#!/usr/bin/bash

set -ex

export PATH=$PATH:/sbin/:/usr/sbin/

./autogen.sh
./configure

# Touch the installation.qcow2, to pretend that it is fresh
[ -f installation.qcow2 ] && touch installation.qcow2

make check

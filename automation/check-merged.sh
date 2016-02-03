#!/bin/bash -xe
echo "check-merged.sh"

set -xe

./autogen.sh
./configure
make -j5 check

#!/bin/bash -xe
echo "check-merged.sh"

set -xe

./autogen.sh
make -j5 check

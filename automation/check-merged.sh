#!/bin/bash -xe
echo "check-merged.sh"

set -xe

PYTHON=/usr/bin/python3 ./autogen.sh
make -j5 check

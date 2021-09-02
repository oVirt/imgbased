#!/bin/bash -xe
echo "check-merged.sh"

# mock runner is not setting up the system correctly
# https://issues.redhat.com/browse/CPDEVOPS-242
dnf install -y $(cat automation/check-merged.packages)

set -xe

PYTHON=/usr/bin/python3 ./autogen.sh
make check

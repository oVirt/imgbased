#!/bin/bash -xe
echo "check-merged.sh"

./autogen.sh && ./configure

die() { echo $@ ; exit 1 ; }

if ! make -j5 check; then
    die "Node check failed"
fi

#!/bin/bash -xe
echo "check-merged.sh"

./autogen.sh && ./configure

if ! make -j5 check; then
    die "Node check failed"
fi

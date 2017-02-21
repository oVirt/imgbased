#!/bin/bash -xe
[[ -d exported-artifacts ]] \
|| mkdir -p exported-artifacts

[[ -d tmp.repos ]] \
|| mkdir -p tmp.repos

rm -rf output

# Run rpmbuild, assuming the tarball is in the project's directory
rpmbuild \
    -D "_topmdir $PWD/tmp.repos" \
    -D "_srcrpmdir $PWD/output" \
    -D "_release 1" \
    -ts imgbased-*.tar.xz

rpmbuild \
    -D "_topmdir $PWD/tmp.repos" \
    -D "_rpmdir $PWD/output" \
    -D "_release 1" \
    --rebuild $PWD/output/imgbased-*.src.rpm

mv *.tar.xz exported-artifacts
find \
    "$PWD/output" \
    -iname \*.rpm \
    -exec mv {} exported-artifacts/ \;

# vim: et sts=2 sw=2

set -xe

export ARTIFACTSDIR=$PWD/exported-artifacts
export PATH=$PATH:/sbin:/usr/sbin


build() {
  ./autogen.sh
  make rpm

  mkdir "$ARTIFACTSDIR"

  find rpmbuild -name "*.rpm" -exec mv -v {} "$ARTIFACTSDIR/" \;

  ls -shal "$ARTIFACTSDIR/" || :
}

build

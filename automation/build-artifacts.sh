# vim: et sts=2 sw=2

set -x

export ARTIFACTSDIR=$PWD/exported-artifacts
export PATH=$PATH:/sbin:/usr/sbin

prepare() {
  git submodule update --init --recursive
}

build() {
  ./autogen.sh && ./configure
  make rpm

  mkdir "$ARTIFACTSDIR"

  find rpmbuild -name "*.rpm" -exec mv -v {} "$ARTIFACTSDIR/" \;

  ls -shal "$ARTIFACTSDIR/" || :
}

prepare
build

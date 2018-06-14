# vim: et sts=2 sw=2

set -xe

export ARTIFACTSDIR=$PWD/exported-artifacts
export PATH=$PATH:/sbin:/usr/sbin

build() {
  ./autogen.sh

  mkdir "$ARTIFACTSDIR"

  IFS=- read _ _ rel sha <<< $(git describe --tags --match "imgbased*")

  if [[ -n $sha ]]; then # Not tagged, build as before (or add $rel??)
    make rpm
  else
    make rpm DEF_RELEASE=
    find -name "*.tar.xz" -exec mv -v {} "$ARTIFACTSDIR/" \;
  fi

  find rpmbuild -name "*.rpm" -exec mv -v {} "$ARTIFACTSDIR/" \;

  ls -shal "$ARTIFACTSDIR/" || :
}

build

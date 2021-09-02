# vim: et sts=2 sw=2

set -xe

# mock runner is not setting up the system correctly
# https://issues.redhat.com/browse/CPDEVOPS-242
dnf install -y $(cat automation/build-artifacts.packages)

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

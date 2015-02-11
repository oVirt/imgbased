#
# Adding upstream oVirt vdsm
#
%pre
set -x
OVIRT_SLOT=3.5
DIST=fc
REPOFILE="http://gerrit.ovirt.org/gitweb?p=ovirt-release.git;a=blob_plain;f=ovirt-release-${OVIRT_SLOT}/ovirt.repo.in"

mkdir -p /tmp/yum.repos.d/
curl "${REPOFILE}" \
  | sed "s/@DIST@/${DIST}/g ; s/@OVIRT_SLOT@/${OVIRT_SLOT}/g" \
  > /tmp/yum.repos.d/ovirt.repo

%end

%packages
vdsm
%end

#
# Adding upstream oVirt vdsm
#
%post
set -x
yum install -y http://plain.resources.ovirt.org/pub/yum-repo/ovirt-release35.rpm
yum install -y vdsm
%end

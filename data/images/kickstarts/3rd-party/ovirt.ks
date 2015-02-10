#
# Adding upstream oVirt vdsm
#
%pre
yum install -y http://resources.ovirt.org/pub/yum-repo/ovirt-release35.rpm
%end

%packages
vdsm
%end

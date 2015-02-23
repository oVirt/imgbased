#
# Add docker
#
%post
set -x
grep -qi fedora /etc/system-release && yum install -y docker-io
grep -qi centos /etc/system-release && yum install -y docker
%end

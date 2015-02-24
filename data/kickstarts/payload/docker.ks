#
# Add docker
#
%post
set -x
grep -i fedora /etc/system-release && yum install -y docker-io
grep -i centos /etc/system-release && yum install -y docker
%end

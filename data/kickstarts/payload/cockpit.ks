#
# Adds the latest cockpit bits
#
%post
set -x
grep -i fedora /etc/system-release && yum-config-manager --add-repo="https://copr.fedoraproject.org/coprs/sgallagh/cockpit-preview/repo/fedora-20/sgallagh-cockpit-preview-fedora-20.repo"
grep -i centos /etc/system-release && yum-config-manager --add-repo="https://copr.fedoraproject.org/coprs/sgallagh/cockpit-preview/repo/epel-7/sgallagh-cockpit-preview-epel-7.repo"
yum install -y cockpit
%end

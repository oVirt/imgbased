#
# Adds the latest cockpit bits
#
%post
set -x
yum-config-manager --add-repo="https://copr.fedoraproject.org/coprs/sgallagh/cockpit-preview/repo/fedora-20/sgallagh-cockpit-preview-fedora-20.repo"
yum install -y cockpit
%end

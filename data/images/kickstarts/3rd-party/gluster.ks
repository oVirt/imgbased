#
# Adding gluster from upstream
#
%pre
set -x
mkdir -p /tmp/yum.repos.d/
curl -o /tmp/yum.repos.d/glusterfs-fedora.repo "http://download.gluster.org/pub/gluster/glusterfs/LATEST/Fedora/glusterfs-fedora.repo"
%end

# Taken from http://www.gluster.org/documentation/quickstart/index.html
%packages
glusterfs
glusterfs-server
glusterfs-fuse
glusterfs-geo-replication
%end

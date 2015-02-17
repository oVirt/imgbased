#
# Adding gluster from upstream
#
%post
set -x
yum-config-manager --add-repo="http://download.gluster.org/pub/gluster/glusterfs/LATEST/Fedora/glusterfs-fedora.repo"
yum install -y glusterfs glusterfs-server glusterfs-fuse glusterfs-geo-replication glusterfs-api glusterfs-cli
%end

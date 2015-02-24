#
# Adding gluster from upstream
#
%post
set -x
grep -i fedora /etc/system-release && yum-config-manager --add-repo="http://download.gluster.org/pub/gluster/glusterfs/LATEST/Fedora/glusterfs-fedora.repo"
grep -i centos /etc/system-release && yum-config-manager --add-repo="http://download.gluster.org/pub/gluster/glusterfs/LATEST/CentOS/glusterfs-epel.repo"
yum install -y glusterfs glusterfs-server glusterfs-fuse glusterfs-geo-replication glusterfs-api glusterfs-cli
%end

#
# Adding gluster from upstream
#
%pre
yum-config-manager --add-repo="http://download.gluster.org/pub/gluster/glusterfs/LATEST/Fedora/glusterfs-fedora.repo"
%end

# Taken from http://www.gluster.org/documentation/quickstart/index.html
%packages
glusterfs
glusterfs-server
glusterfs-fuse
glusterfs-geo-replication
%end

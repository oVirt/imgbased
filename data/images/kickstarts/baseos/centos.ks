
#
# CentOS repositories
#
url --mirrorlist=http://mirrorlist.centos.org/mirrorlist?repo=os&release=$releasever&arch=$basearch
repo --name=updates --mirrorlist=http://mirrorlist.centos.org/mirrorlist?repo=updates&release=$releasever&arch=$basearch

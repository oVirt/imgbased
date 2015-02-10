
#
# CentOS repositories
#
url --mirrorlist=http://mirrorlist.centos.org/?repo=os&release=$releasever&arch=$basearch
repo --name=updates --mirrorlist=http://mirrorlist.centos.org/?repo=updates&release=$releasever&arch=$basearch
repo --name=extra --mirrorlist=http://mirrorlist.centos.org/?repo=extras&release=$releasever&arch=$basearch

#
# Additional cockpit dependencies
#
repo --name=virt7-testing --baseurl=http://cbs.centos.org/repos/virt7-testing/$basearch/os/

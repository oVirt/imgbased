
%include ../partial/header.ks
%include ../partial/firstboot.ks
%include ../partial/testing.ks

#
# Now custom parts
#

#
# Storage configuration
#
clearpart --all --initlabel --disklabel=gpt
bootloader --timeout=1
autopart --type=thinp --fstype=ext4

#
# Installation source (image/tarball)
#
liveimg --url=@ROOTFS_URL@

#
# Create a layer after installation
#
%post --erroronfail
imgbase --debug layer --add
%end

#
# Post installation configuration
#
# Configure simple networking on installation
network --bootproto=dhcp
# … poweroff because we are likely in a VM
poweroff

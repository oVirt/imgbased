
%include ../partial/header.ks
%include ../partial/storage.ks
%include ../partial/firstboot.ks
%include ../partial/testing.ks

#
# Now custom parts
#

# Install from an image/tarball
liveimg --url=@ROOTFS_URL@

# Create a layer after installation
%post --erroronfail
imgbase --debug layer --add
%end

# Do not reconfigure, because we did this during the installation
firstboot --disable

# Configure simple networking on installation
network --bootproto=dhcp

# … poweroff because we are likely in a VM
poweroff


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
imgbase layer --add
%end

# Reboto after installation, if we were on real hardware
#reboot

# … poweroff because we are likely in a VM
poweroff

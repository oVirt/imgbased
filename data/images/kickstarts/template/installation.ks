
%include ../partial/header.ks
%include ../partial/storage.ks
%include ../partial/firstboot.ks
%include ../partial/post-testing.ks

#
# Now custom parts
#

# Install from an image/tarball
liveimg --url=@ROOTFS_URL@

# Create a layer after installation
%post
imgbase layer --add
%end

# Reboto after installation
reboot

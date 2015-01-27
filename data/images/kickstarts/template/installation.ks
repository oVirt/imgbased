
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
set -ex
imgbase --debug layer --add
#sed -i "s/Image\(-\+\)0.0/Image\10.1/ig" /etc/fstab
#dracut -f
lvs
lvchange --setactivationskip n HostVG/Image-0.0
lvs
%end

%post --nochroot
#echo "Create the new layer"
#lvcreate --snapshot --name HostVG/Image-0.1 HostVG/Image-0.0
#tune2fs -u random -L Image-0.1 /dev/HostVG/Image-0.1

#echo "Disable the base"
%end

# Reboto after installation, if we were on real hardware
#reboot

# … poweroff because we are likely in a VM
poweroff

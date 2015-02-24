
%include ../partial/header.ks
%include ../partial/firstboot.ks
%include ../partial/testing.ks

#
# Now custom parts
#

#
# Storage configuration
#
clearpart --all --initlabel # --disklabel=gpt
bootloader --timeout=1
part biosboot --size=1 --fstype biosboot
part /boot --size=512 --fstype ext4 --label=Boot --asprimary
part pv.01 --grow
volgroup HostVG pv.01
# FIXME Drop chunksize in future: https://bugzilla.redhat.com/show_bug.cgi?id=1195857
logvol none --vgname=HostVG --name=ImagePool --size=3072 --grow --thinpool --chunksize=1024
logvol /    --vgname=HostVG --name=Image-0.0 --size=3072 --thin --poolname=ImagePool --fstype=ext4 --fsoptions=discard
logvol /var --vgname=HostVG --name=Data      --size=5120 --thin --poolname=ImagePool --fstype=ext4 --fsoptions=discard
logvol swap --vgname=HostVG                  --size=1024 --fstype=swap

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

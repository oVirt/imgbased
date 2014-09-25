

##
## Including ../partial/header.ks
##

#
# Header
#
lang en_US.UTF-8
keyboard us
timezone --utc Etc/UTC
auth --enableshadow --passalgo=sha512
selinux --permissive
network --bootproto=dhcp
rootpw THISISJUSTADUMMY
firstboot --disable

#reboot
poweroff


##
## Including ../partial/storage.ks
##
clearpart --all --initlabel
bootloader --append="console=ttyS0 quiet" --timeout=1

part biosboot --size=1
part /boot --size=512 --fstype ext4 --label=Boot --asprimary

part pv.01 --size 5000
volgroup HostVG pv.01
logvol /config --vgname=HostVG --size=64 --name=Config --fstype=ext4
logvol none --vgname=HostVG --size=4000 --name=ImagePool --thinpool --chunksize=128 --metadatasize=4
logvol / --vgname=HostVG --size=3000 --name=Image-0.0 --thin --poolname=ImagePool --fstype=ext4 --fsoptions=discard
logvol swap --vgname=HostVG --fstype=swap

##
## Including ../partial/firstboot.ks
##


firstboot --reconfig

%packages
initial-setup
%end

##
## Including ../partial/post-testing.ks
##

#
# Build most recent imagbased for testing
#
%post --erroronfail
echo "Build imgbased"
yum remove -y imgbased
cd /root
git clone https://github.com/fabiand/imgbased.git
cd imgbased
./autogen.sh
./configure
make install
%end

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


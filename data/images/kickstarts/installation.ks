#
# This kickstart covers the installation of the rootfs.
# This kickstart transfers the rootfs to the prepared disks.
#
# Basically this is the kickstart used by the installer.
#

clearpart --all --initlabel
bootloader --append="console=ttyS0" --timeout=1

part biosboot --size=1
part /boot --size=512 --fstype ext4 --label=Boot --asprimary

part pv.01 --size 4096
volgroup HostVG pv.01
logvol /config --vgname=HostVG --size=64 --name=Config --fstype=ext4
logvol / --vgname=HostVG --size=2048 --name=Image-0.0 --fstype=ext4 --fsoptions=discard
#logvol swap --vgname=HostVG --fstype=swap

# Point to rootfs (also used for LiveCD to deploy)
liveimg --url=http://10.0.0.2/runtime-layout.img


##
## Including ../partial/imgbased.ks
##

#
# Install imgbased
#
%post --erroronfail
echo "Build imgbased"
pushd .
yum install -y make git autoconf automake
yum install -y asciidoc yum-plugin-remove-with-leaves
cd /root
git clone https://github.com/fabiand/imgbased.git
cd imgbased
./autogen.sh
make install
#yum remove -y --remove-leaves asciidoc
popd

echo "Enable FDO Bootloader Spec (needed by imgbased)"
echo "echo '# Import BLS entries'" > /etc/grub.d/42_bls
echo "echo bls_import" >> /etc/grub.d/42_bls
chmod a+x /etc/grub.d/42_bls

# Update grub2 cfg
grub2-mkconfig -o /boot/grub2/grub.cfg
#grub2-mkconfig -o /boot/efi/EFI/fedora/grub.cfg


%end

%post --erroronfail
echo "FIXME Creating writeable overlay"
# imgbased
%end


%post --erroronfail
yum install -y anaconda
systemctl enable anaconda.service anaconda-tmux@.service anaconda-direct.service anaconda-shell@.service
%end


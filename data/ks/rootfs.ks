#
# Fedora repositories
#
url --mirrorlist=http://mirrors.fedoraproject.org/mirrorlist?repo=fedora-$releasever&arch=$basearch
repo --name=updates --mirrorlist=http://mirrors.fedoraproject.org/mirrorlist?repo=updates-released-f$releasever&arch=$basearch
#repo --name=updates-testing --mirrorlist=http://mirrors.fedoraproject.org/mirrorlist?repo=updates-testing-f$releasever&arch=$basearch


#
# Some defaults
#
lang en_US.UTF-8
keyboard us
timezone --utc Etc/UTC
auth --enableshadow --passalgo=sha512
selinux --permissive
firstboot --disable

rootpw --lock
user --name=node --lock

poweroff


#
# Storage
#
clearpart --all --initlabel
bootloader --timeout=1
part / --size=3072 --fstype=ext4 --fsoptions=discard

#
# Packages
#
%packages --excludedocs --ignoremissing
@core

# lvm - Needed explicitly, because anaconda would not pull it in
# because it's not needed.
lvm2

# config generic == hostonly, this is needed
# to support make a generic image (do not keep lvm informations in the image)
dracut-config-generic

# EFI support
grub2-efi
shim
efibootmgr

# Some tools
vim-minimal
augeas
tmux
git

# Install, just in case ...
initial-setup
%end


#
# Add custom post scripts after the base post.
#
%post --erroronfail

# setup systemd to boot to the right runlevel
echo "Setting default runlevel to multiuser text mode"
rm -vf /etc/systemd/system/default.target
ln -vs /lib/systemd/system/multi-user.target /etc/systemd/system/default.target

echo "Enable FDO Bootloader Spec"
echo "echo '# Import BLS entries'" > /etc/grub.d/05_bls
echo "echo bls_import" >> /etc/grub.d/05_bls
chmod a+x /etc/grub.d/*_bls

echo "Enable Syslinux configuration"
echo "echo '# Import syslinux entries'" > /etc/grub.d/06_syslinux
echo "echo syslinux_configfile syslinux.cfg" >> /etc/grub.d/06_syslinux
chmod a+x /etc/grub.d/*_syslinux

echo "Cleaning old yum repodata."
yum clean all
%end

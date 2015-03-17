#
# Header
#
lang en_US.UTF-8
keyboard us
timezone --utc Etc/UTC
auth --enableshadow --passalgo=sha512
selinux --permissive
firstboot --disable
network --bootproto=dhcp

rootpw --lock
user --name=node --lock

liveimg --url=@ROOTFS_URL@

clearpart --all --initlabel --disklabel=gpt
bootloader --timeout=1
autopart --type=thinp --fstype=ext4

# … poweroff because we are likely in a VM
poweroff


# Automatically login root and remove the password for testing
%post
set -x
echo "Enabling auto-login of root on all getty instances"
sed -i "/ExecStart/ s/$/ --autologin root/" /lib/systemd/system/*getty*.service

echo "Unlocking root account"
passwd --unlock --delete root
%end


#
# Create a layer after installation
#
%post
set -x
imgbase --debug layout --init-from /
imgbase --debug layer --add
%end

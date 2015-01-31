
#
# Add custom post scripts after the base post.
#
%post --erroronfail

# setup systemd to boot to the right runlevel
echo "Setting default runlevel to multiuser text mode"
rm -vf /etc/systemd/system/default.target
ln -vs /lib/systemd/system/multi-user.target /etc/systemd/system/default.target

echo "Install image-minimizer"
curl -O https://git.fedorahosted.org/cgit/lorax.git/plain/src/bin/image-minimizer
install -m775 image-minimizer /usr/bin

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

echo "Fixing SELinux contexts."
touch /var/log/cron
touch /var/log/boot.log
mkdir -p /var/cache/yum

%end

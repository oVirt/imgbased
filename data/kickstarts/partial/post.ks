
#
# Add custom post scripts after the base post.
#
%post --erroronfail

# setup systemd to boot to the right runlevel
echo "Setting default runlevel to multiuser text mode"
rm -f /etc/systemd/system/default.target
ln -s /lib/systemd/system/multi-user.target /etc/systemd/system/default.target
echo .

#echo "Enable readonly-root"
#sed -i \
#    -e "s/^\(READONLY\)=.*/\1=yes/" \
#    -e "s/^\(TEMPORARY_STATE\)=.*/\1=yes/" \
#    /etc/sysconfig/readonly-root

#echo "Make rootfs ro"
# https://bugzilla.redhat.com/show_bug.cgi?id=1082085
#sed -i "s/subvol=Origin/subvol=Origin,ro/" /etc/fstab

#echo "Enable docker"
#systemctl enable docker.service || :

#echo "Enable openvswitch"
#systemctl enable openvswitch.service || :

#echo "Enable cockpit"
#systemctl enable cockpit.service || :

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

echo "Install image-minimizer"
curl -O https://git.fedorahosted.org/cgit/lorax.git/plain/src/bin/image-minimizer
install -m775 image-minimizer /usr/bin

echo "Enable FDO Bootloader Spec"
echo "echo '# Import BLS entries'" > /etc/grub.d/42_bls
echo "echo bls_import" >> /etc/grub.d/42_bls
chmod a+x /etc/grub.d/42_bls
# Update grub2 cfg
grub2-mkconfig -o /boot/grub2/grub.cfg
#grub2-mkconfig -o /boot/efi/EFI/fedora/grub.cfg

echo "Getty fixes"
# although we want console output going to the serial console, we don't
# actually have the opportunity to login there. FIX.
# we don't really need to auto-spawn _any_ gettys.
sed -i '/^#NAutoVTs=.*/ a\
NAutoVTs=0' /etc/systemd/logind.conf

echo "Fix missing console device"
/bin/mknod /dev/console c 5 1

echo "Cleaning old yum repodata."
yum clean all

echo "Fixing SELinux contexts."
touch /var/log/cron
touch /var/log/boot.log
mkdir -p /var/cache/yum

# have to install policycoreutils to run this... commenting for now
/usr/sbin/fixfiles -R -a restore

%end

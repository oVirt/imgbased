
#
# Packages
#
%packages --excludedocs --nobase
@core
vim-minimal
grub2-efi
shim
dnf
augeas

anaconda-core
anaconda-tui

screen
#docker-io
#openvswitch

# See: https://admin.fedoraproject.org/updates/FEDORA-2014-2081/cockpit-0.2-0.4.20140204git5e1faad.fc20
#cockpit


# Some things from @core we can do without inside the container
-biosdevname

%end


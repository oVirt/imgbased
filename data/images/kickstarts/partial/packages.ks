
#
# Packages
#
%packages --excludedocs
@core

# In F21 --nocore is available, then we use this list
# to provide the minimal set of packages
#kernel
#systemd
#bash
#NetworkManager
#yum

# Only available in Fedora 20+
#anaconda-core
#anaconda-tui
#cockpit

vim-minimal
grub2-efi
shim
augeas

screen
#docker-io
#openvswitch

# Some things from @core we can do without inside the container
-biosdevname

%end


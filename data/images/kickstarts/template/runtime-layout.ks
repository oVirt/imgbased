
%include ../partial/header.ks

clearpart --all --initlabel
bootloader --append="console=ttyS0 quiet trulyquiet" --timeout=1

part biosboot --size=1
part /boot --size=512 --fstype ext4 --label=Boot --asprimary

part pv.01 --size 5000
volgroup HostVG pv.01
logvol /config --vgname=HostVG --size=64 --name=Config --fstype=ext4
logvol none --vgname=HostVG --size=4000 --name=ImagePool --thinpool --chunksize=128
logvol / --vgname=HostVG --size=3000 --name=Image-0.0 --thin --poolname=ImagePool --fstype=ext4 --fsoptions=discard
#logvol swap --vgname=HostVG --fstype=swap 

%post
echo "Enabling auto-login of root on all getty instances"
sed -i "/ExecStart/ s/$/ --autologin root/" /lib/systemd/system/*getty*.service
%end

%include ../partial/repositories.ks
%include ../partial/packages.ks
%include ../partial/packages-testing.ks
%include ../partial/post.ks
%include ../partial/post-testing.ks
%include ../partial/minimization.ks

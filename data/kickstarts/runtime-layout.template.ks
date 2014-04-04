
%include header.partial.ks

clearpart --all --initlabel
bootloader --append="console=ttyS0" --timeout=1

part biosboot --size=1
part /boot --size=512 --fstype ext4 --label=Boot --asprimary

part pv.01 --size 4096
volgroup HostVG pv.01
logvol /config --vgname=HostVG --size=64 --name=Config --fstype=ext4
logvol none --vgname=HostVG --size=3072 --name=ImagePool --thinpool --chunksize=128
logvol / --vgname=HostVG --size=2048 --name=Image-0.0 --thin --poolname=ImagePool --fstype=ext4 --fsoptions=discard
#logvol swap --vgname=HostVG --fstype=swap 

%include repositories.partial.ks
%include packages.partial.ks
%include post.partial.ks


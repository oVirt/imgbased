clearpart --all --initlabel --disklabel=gpt

bootloader --timeout=1

part biosboot --size=1 --fstype biosboot
part /boot --size=512 --fstype ext4 --label=Boot --asprimary

part pv.01 --size 5120
volgroup HostVG pv.01
logvol none --vgname=HostVG --size=4096 --name=ImagePool --thinpool
logvol / --vgname=HostVG --size=3072 --name=Image-0.0 --thin --poolname=ImagePool --fstype=ext4 --fsoptions=discard

# We assume that no overprovisioning is happening
#logvol swap --vgname=HostVG --fstype=swap --size=1024

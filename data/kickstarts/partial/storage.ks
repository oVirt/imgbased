clearpart --all --initlabel # --disklabel=gpt

bootloader --timeout=1

part biosboot --size=1 --fstype biosboot
part /boot --size=512 --fstype ext4 --label=Boot --asprimary

part pv.01 --grow
volgroup HostVG pv.01
logvol none --vgname=HostVG --name=ImagePool --size=3072 --grow --thinpool
logvol /    --vgname=HostVG --name=Image-0.0 --size=3072 --thin --poolname=ImagePool --fstype=ext4 --fsoptions=discard
logvol /var --vgname=HostVG --name=Data      --size=5120 --thin --poolname=ImagePool --fstype=ext4 --fsoptions=discard
logvol swap --vgname=HostVG                  --size=1024 --fstype=swap

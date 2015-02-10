
%include ../partial/header.ks

clearpart --all --initlabel

bootloader --timeout=1
poweroff

part / --size=3072 --fstype=ext4 --label=Image-0.0 --fsoptions=discard

%include ../partial/os.ks
%include ../partial/packages.ks
%include ../partial/post.ks
%include ../partial/firstboot.ks

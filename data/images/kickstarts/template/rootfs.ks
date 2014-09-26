
%include ../partial/header.ks

clearpart --all --initlabel
bootloader --append="console=ttyS0" --timeout=1
poweroff

part / --size=3096 --fstype=ext4 --label=Image-0.0 --fsoptions=discard

%include ../partial/repositories.ks
%include ../partial/packages.ks
%include ../partial/post.ks
%include ../partial/minimization.ks

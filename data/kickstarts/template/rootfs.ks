
%include ../partial/header.ks

clearpart --all --initlabel

bootloader --timeout=1
poweroff

part / --size=3072 --fstype=ext4 --label=Image-0.0 --fsoptions=discard

%post
# Empty fstab, it wil be rewritten
# https://github.com/rhinstaller/lorax/blob/master/README.livemedia-creator#L121
:> /etc/fstab
%end

%include ../partial/packages.ks
%include ../partial/post.ks
%include ../partial/firstboot.ks

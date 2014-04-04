
%include header.partial.ks

clearpart --all --initlabel
bootloader --append="console=ttyS0" --timeout=1

part / --size=2048 --fstype=ext4 --label=Image-0.0 --fsoptions=discard

%include repositories.partial.ks
%include packages.partial.ks
%include post.partial.ks

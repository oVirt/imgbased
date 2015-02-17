%include rootfs.ks

%post --erroronfail
yum install -y anaconda
systemctl enable anaconda.service anaconda-tmux@.service anaconda-direct.service anaconda-shell@.service
%end


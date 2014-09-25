
%include ../partial/header.ks

%include ../partial/storage.ks

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

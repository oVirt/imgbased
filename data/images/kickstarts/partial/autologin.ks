%post
echo "Enabling auto-login of root on all getty instances"
sed -i "/ExecStart/ s/$/ --autologin root/" /lib/systemd/system/*getty*.service
%end


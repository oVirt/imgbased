
#
# Configure the system to test the latest imgbased
#

# SOme imgbase build dependencies
%packages
python-nose
python-sh
make
git
autoconf
automake
asciidoc
yum-plugin-remove-with-leaves
%end

# Build most recent imagbased for testing
%post --erroronfail
echo "Build imgbased"
yum remove -y imgbased || :

cd /root
git clone https://github.com/fabiand/imgbased.git
cd imgbased
./autogen.sh
./configure
make install
%end

# Automatically login root and remove the password for testing
%post
echo "Enabling auto-login of root on all getty instances"
sed -i "/ExecStart/ s/$/ --autologin root/" /lib/systemd/system/*getty*.service

echo "Unlocking root account"
passwd --unlock --delete root
%end

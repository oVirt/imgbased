
#
# Build most recent imagbased for testing
#
%post --erroronfail
echo "Build imgbased"
yum remove -y imgbased
cd /root
git clone https://github.com/fabiand/imgbased.git
cd imgbased
./autogen.sh
./configure
make install
%end

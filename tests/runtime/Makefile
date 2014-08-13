
check-local:
	[ -f $(IMAGE) ]
	python -u testrunner.py $(IMAGE) $(PWD) "set -x ; make check-local-inner 2>&1 | tee check-local-inner.log ; init 0"

#
# This target is run inside the VM
#
check-local-inner:
	nm-online
	cd /root/imgbased && git pull && ./autogen.sh && ./configure && make install
	pwd
	ls
	nosetests --verbose --no-byte-compile --with-xunit

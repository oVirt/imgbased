
check-local:
	[ -f $(IMAGE) ]
	python testrunner.py $(IMAGE) $(PWD) "make check-local-inner ; init 0"

#
# This target is run inside the VM
#
check-local-inner:
	nm-online
	cd /root/imgbased && git pull && ./autogen.sh && ./configure && make install
	pwd
	ls
	nosetests --verbose --no-byte-compile --with-xunit

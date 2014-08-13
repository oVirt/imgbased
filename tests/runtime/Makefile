
check-local:
	[ -f $(IMAGE) ]
	python testrunner.py $(IMAGE) $(PWD) "nm-online ; pwd ; ls ; nosetests --verbose --no-byte-compile --with-xunit ; init 0"

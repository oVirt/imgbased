
check-local:
	[ -f $(IMAGE) ]
	python testrunner.py $(IMAGE) $(PWD) "nm-online ; pwd ; ls ; nosetests -v --with-xunit ; init 0"

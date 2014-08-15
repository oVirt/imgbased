
RUNTIMEDIR=tests/runtime
INNERLOG=check-local-inner.log
#
# This target will start the VM
# Within the VM it will call check-local-inner
#
check-local:
	[ -f $(IMAGE) ]
	python -u $(RUNTIMEDIR)/testrunner.py $(IMAGE) $(PWD) "set -x ; make -f $(RUNTIMEDIR)/Makefile check-local-inner 2>&1 | tee $(INNERLOG) ; init 0"

#
# This target is run inside the VM
# It will go into the runtime dir and run those tests
#
check-local-inner:
	nm-online
	git describe --always
	pwd
	export PATH=$(PWD)/scripts/:$$PATH PYTHONPATH=$(PWD)/src ; cd $(RUNTIMEDIR) && nosetests --verbose --no-byte-compile --with-xunit

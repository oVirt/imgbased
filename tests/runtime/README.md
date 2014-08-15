How runtime testing works
=========================

In short:

* a VM is spawned and the srcdir is mounted into the VM using 9pfs
  testrunner.py
* make is used to call the relevant target
  make check-local-inner
* the unittests in the tests/runtime/ dir are run from within the VM
  testSanity.py

There are a couple of assumptions:

* The VM is booting into a bash prompt
* The VM supports 9pfs

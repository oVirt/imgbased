
SHELL := /bin/bash

SUBDIRS =

TEST_LOG_DRIVER = env AM_TAP_AWK='$(AWK)' $(SHELL) \
                  $(top_srcdir)/tap-driver.sh
TESTS = tests/check_python.test tests/check_packaging.test

hooksdir = $(prefix)/lib/imgbased/hooks.d/
pyimagebaseddir = $(pythondir)/imgbased

dist_sbin_SCRIPTS = \
  data/imgbase

dist_pyimagebased_PYTHON = \
  src/__init__.py \
  src/imgbase.py

dist_hooks_SCRIPTS = \
  data/hooks/persistence

EXTRA_DIST = \
  README.md \
  imgbased.spec \
  $(TESTS) \
  tests/common.sh

DERIVED_KS = data/kickstarts/rootfs.ks \
  data/kickstarts/runtime-layout.ks

dist_doc_DATA = \
  data/kickstarts/flatten.py \
  data/kickstarts/rootfs.template.ks \
  data/kickstarts/runtime-layout.template.ks \
  data/kickstarts/repositories.partial.ks \
  data/kickstarts/packages.partial.ks \
  data/kickstarts/header.partial.ks \
  data/kickstarts/post.partial.ks \
  $(DERIVED_KS)

%.ks: %.template.ks
	./data/kickstarts/flatten.py "$<" > "$@"

boot.iso:
	echo "Please fetch any boot.iso from the desired Fedora release"

%.img: data/kickstarts/%.ks
	sudo -E livemedia-creator --make-disk --ks "$<" --iso boot.iso \
	    --vcpus 4 --image-name "$@"
	sudo mv "/var/tmp/$@" .

rpm: dist
	rpmbuild -ta $(DIST_ARCHIVES)

CLEANFILES = $(DERIVED_KS)


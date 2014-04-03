
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


dist_doc_DATA = \
  data/kickstarts/rootfs.ks \
  data/kickstarts/runtime-layout.ks \
  data/kickstarts/rootfs.template.ks \
  data/kickstarts/runtime-layout.template.ks \
  data/kickstarts/repositories.partial.ks \
  data/kickstarts/packages.partial.ks \
  data/kickstarts/header.partial.ks \
  data/kickstarts/post.partial.ks


%.ks:
	ksflatten --config="$*.template.ks" --output="$@"


EXTRA_DIST = \
  README.md \
  imgbased.spec \
  $(TESTS) \
  tests/common.sh

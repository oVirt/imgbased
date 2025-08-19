AUTOMAKE_OPTIONS=-Wno-override
CLEANFILES=

SHELL := /bin/bash

TMPDIR = tmp
TMPREPOS = tmp.repos

hooksdir = $(pkgdatadir)/hooks.d/
pyimagebaseddir = $(pythondir)/@PACKAGE_NAME@
pyimagebasedpluginsdir = $(pyimagebaseddir)/plugins

.PHONY: check check-code check-build distcheck
.SILENT: check check-pyflakes check-codestyle check-pytest check-build distcheck

vpath $(srcdir)

dist_sbin_SCRIPTS = \
  scripts/imgbase

dist_pyimagebased_PYTHON = \
  $(srcdir)/src/imgbased/bootloader.py \
  $(srcdir)/src/imgbased/bootsetup.py \
  $(srcdir)/src/imgbased/command.py \
  $(srcdir)/src/imgbased/hooks.py \
  $(srcdir)/src/imgbased/imgbase.py \
  $(srcdir)/src/imgbased/__init__.py \
  $(srcdir)/src/imgbased/local.py \
  $(srcdir)/src/imgbased/lvm.py \
  $(srcdir)/src/imgbased/__main__.py \
  $(srcdir)/src/imgbased/naming.py \
  $(srcdir)/src/imgbased/openscap.py \
  $(srcdir)/src/imgbased/timeserver.py \
  $(srcdir)/src/imgbased/utils.py \
  $(srcdir)/src/imgbased/volume.py \
  src/imgbased/constants.py

dist_pyimagebasedplugins_PYTHON = \
  $(srcdir)/src/imgbased/plugins/*.py

dist_hooks_SCRIPTS = \
  data/hooks/persistence \
  data/hooks/rebase

EXTRA_DIST = \
  autogen.sh \
  README.md \
  LICENSE \
  packaging/rpm/imgbased.spec \
  src/plugin-dnf/imgbased-persist.conf \
  src/plugin-dnf/imgbased-persist.py \
  src/plugin-yum/imgbased-persist.py \
  src/plugin-yum/imgbased-persist.conf \
  data/imgbased-pool.profile \
  data/imgbase-setup.service \
  tests/*.py
  $(NULL)

dist_doc_DATA = \
  docs/imgbase.asc \
  docs/imgbase.8.asc

man8_MANS = \
  docs/imgbase.8

doc: $(doc_DATA) $(dist_doc_DATA) $(man8-MANS)


doc: $(man8_MANS)

docs/imgbase.8: docs/imgbase.8.asc

rpm:DEF_RELEASE=--define "_release @RELEASE@@REVISION@"
rpm: dist
	rpmbuild $(RPMBUILD_ARGS) $(DEF_RELEASE) -ta $(DIST_ARCHIVES)

rpm-build-deps:
	grep "Require" packaging/rpm/imgbased.spec | cut -d: -f2-

%: %.xml
	xsltproc -o $@ -nonet \
	http://docbook.sourceforge.net/release/xsl/current/manpages/docbook.xsl $<

%.xml: %.asc
	mkdir -p $$(dirname $@)
	asciidoc -d manpage -b docbook -o $@ $<


SRCFILES = $(shell find . -xdev -name \*.py)

check-build: $(SRCFILES)
	@echo "[CHECK] rpmbuild"
	./autogen.sh
	make -s rpm doc

export PYTHONPATH=src/

check-pyflakes: $(SRCFILES)
	@echo "[CHECK] pyflakes"
	find . -xdev -name \*.py | xargs pyflakes

check-codestyle: $(SRCFILES)
if HAVE_CODESTYLE_CHECKER
	@echo "[CHECK] @CODESTYLE_CHECKER@"
	find . -xdev -name \*.py | xargs @CODESTYLE_CHECKER@
else
	@echo "[CHECK] Codestyle checker not found, skipping"
endif

check-pytest: $(SRCFILES)
if HAVE_PYTEST
	@echo "[CHECK] @PYTEST@"
	@PYTEST@ tests/
else
	@echo "[CHECK] pytest not found, skipping"
endif


check-code: check-pyflakes check-codestyle check-pytest

check: check-code check-build
	@echo "PASS"

distcheck: export RPMBUILD_ARGS=--define="_topdir `pwd`/$(TMPDIR)/$(TMPREPOS)"
distcheck:
	$(MAKE) dist
	rm -rf $(TMPDIR) && \
	mkdir $(TMPDIR) && \
	cd $(TMPDIR) && \
	tar xf ../imgbased-@PACKAGE_VERSION@.tar.xz -C . --strip 1 && \
	./autogen.sh && $(MAKE) check
	rm -rf $(TMPDIR)

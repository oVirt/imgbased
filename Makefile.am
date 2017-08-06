AUTOMAKE_OPTIONS=-Wno-override
CLEANFILES=

SHELL := /bin/bash

TMPDIR = tmp
TMPREPOS = tmp.repos

hooksdir = $(pkgdatadir)/hooks.d/
pyimagebasedpluginsdir = $(pyimagebaseddir)/plugins

.PHONY: check check-code check-build distcheck
.SILENT: check check-pyflakes check-pep8 check-nosetests check-build distcheck

vpath $(srcdir)

dist_sbin_SCRIPTS = \
  scripts/imgbase \
  scripts/imgbase-copy-bootfiles

dist_pyimagebased_PYTHON = \
  src/imgbased/*.py

dist_pyimagebasedplugins_PYTHON = \
  src/imgbased/plugins/*.py

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
  data/imgbase-clean-grub.service \
  data/imgbase-copy-bootfiles.service \
  data/imgbase-generate-iqn.service \
  data/imgbase-config-vdsm.service \
  data/imgbase-firstboot.service \
  data/imgbased-pool.profile \
  docs/imgbase-copy-bootfiles.8 \
  scripts/grub/09_node \
  tests/*.py
  $(NULL)

dist_doc_DATA = \
  docs/imgbase.asc \
  docs/imgbase.8.asc

man8_MANS = \
  docs/imgbase.8 \
  docs/imgbase-copy-bootfiles.8

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

check-pep8: $(SRCFILES)
	@echo "[CHECK] pep8"
	find . -xdev -name \*.py | xargs pep8

check-nosetests: $(SRCFILES)
	@echo "[CHECK] nosetests"
	nosetests --no-byte-compile --with-xunit \
		--with-coverage --cover-erase --cover-tests \
		--cover-branches --cover-inclusive \
		--cover-package=imgbased --cover-xml --cover-min-percentage=45 \
		--with-doctest --doctest-tests


check-code: check-pyflakes check-pep8 check-nosetests

check: check-code check-build
	@echo "PASS"

distcheck: export RPMBUILD_ARGS=--define="_topdir `pwd`/$(TMPDIR)/$(TMPREPOS)"
distcheck:
	$(MAKE) dist
	rm -rf $(TMPDIR) && \
	mkdir $(TMPDIR) && \
	cd $(TMPDIR) && \
	tar xf ../imgbased-@PACKAGE_VERSION@.tar.xz -C . --strip 1 && \
	./autogen.sh && \
	$(MAKE) check
	rm -rf $(TMPDIR)


CLEANFILES=

SHELL := /bin/bash

hooksdir = $(pkgdatadir)/hooks.d/
pyimagebaseddir = $(pythondir)/$(PACKAGE_NAME)
pyimagebasedpluginsdir = $(pyimagebaseddir)/plugins

.PHONY: check check-code check-build
.SILENT: check check-pyflakes check-pep8 check-nosetests check-build

vpath $(srcdir)

dist_sbin_SCRIPTS = \
  scripts/imgbase

dist_pyimagebased_PYTHON = \
  src/imgbased/*.py

dist_pyimagebasedplugins_PYTHON = \
  src/imgbased/plugins/*.py

dist_hooks_SCRIPTS = \
  data/hooks/persistence \
  data/hooks/rebase

EXTRA_DIST = \
  README.md \
  LICENSE \
  packaging/rpm/imgbased.spec \
  tests/*.py

dist_doc_DATA = \
  docs/imgbase.asc \
  docs/imgbase.8.asc

man8_MANS = docs/imgbase.8

doc: $(doc_DATA) $(dist_doc_DATA) $(man8-MANS)


doc: $(man8_MANS)

docs/imgbase.8: docs/imgbase.8.asc

rpm:DEF_RELEASE=--define "_release 0.$$(date +%Y%m%d%H%M)git$$(git log -n1 --format=%h)"
rpm: dist
	rpmbuild $(DEF_RELEASE) -ta $(DIST_ARCHIVES)

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
	./autogen.sh &> $@.log
	make -s dist &>> $@.log
	make -s doc &>> $@.log
	rpmbuild --quiet --nocheck -ta imgbase*.tar.xz &>> $@.log


export PYTHONPATH=src/

check-pyflakes: $(SRCFILES)
	@echo "[CHECK] pyflakes"
	find . -xdev -name \*.py | xargs python3-pyflakes

check-pep8: $(SRCFILES)
	@echo "[CHECK] pep8"
	find . -xdev -name \*.py | xargs python3-pep8

check-pylint: $(SRCFILES)
	@echo "[CHECK] pylint"
	find . -xdev -name \*.py | xargs echo pylint

check-nosetests: $(SRCFILES)
	@echo "[CHECK] nosetests"
	nosetests --no-byte-compile --with-xunit \
		--with-coverage --cover-erase --cover-tests --cover-branches --cover-inclusive --cover-package=imgbased --cover-xml \
		--with-doctest --doctest-tests &> $@.log


check-code: check-pyflakes check-pep8 check-nosetests

check: check-code check-build
	@echo "PASS"

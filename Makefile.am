
CLEANFILES=

SHELL := /bin/bash

hooksdir = $(pkgdatadir)/hooks.d/
pyimagebaseddir = $(pythondir)/$(PACKAGE_NAME)
pyimagebasedpluginsdir = $(pyimagebaseddir)/plugins
yumplugindir = $(prefix)/lib/yum-plugins/
yumpluginconfdir = $(sysconfdir)/yum/pluginconf.d/

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

dist_yumplugin_SCRIPTS = \
        src/plugin-yum/imgbased-warning.py \
        $(NULL)

dist_yumpluginconf_SCRIPTS = \
        src/plugin-yum/imgbased-warning.conf \
        $(NULL)

EXTRA_DIST = \
  README.md \
  LICENSE \
  packaging/rpm/imgbased.spec \
  src/plugin-dnf/imgbased-warning.py \
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
		--cover-package=imgbased --cover-xml --cover-min-percentage=51 \
		--with-doctest --doctest-tests


check-code: check-pyflakes check-pep8 check-nosetests

check: check-code check-build
	@echo "PASS"

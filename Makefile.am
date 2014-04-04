
SHELL := /bin/bash


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
  docs/imgbase.8.asc

doc_DATA = \
  $(DERIVED_KS)

man8_MANS = docs/imgbase.8

boot.iso:
	echo "Please fetch any boot.iso from the desired Fedora release"

doc: $(manpages)

docs/imgbase.8: docs/imgbase.asc

%.ks: %.template.ks
	./data/kickstarts/flatten.py "$<" > "$@"

%: %.xml
	xsltproc -o $@ -nonet \
	http://docbook.sourceforge.net/release/xsl/current/manpages/docbook.xsl $<

%.xml: %.asc
	asciidoc -d manpage -b docbook -o $@ $<

%.img: data/kickstarts/%.ks
	sudo -E livemedia-creator --make-disk --ks "$<" --iso boot.iso \
	    --vcpus 4 --image-name "$@"
	sudo mv "/var/tmp/$@" .

rpm:DEF_RELEASE=--define "_release 0.$$(date +%Y%m%d%H%M)git$$(git log -n1 --format=%h)"
rpm: dist
	rpmbuild $(DEF_RELEASE) -ta $(DIST_ARCHIVES)

CLEANFILES = $(DERIVED_KS)


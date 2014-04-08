
SHELL := /bin/bash

TEST_LOG_DRIVER = env AM_TAP_AWK='$(AWK)' $(SHELL) \
                  $(top_srcdir)/build-aux/tap-driver.sh
TESTS = tests/package/check_python.test tests/package/check_packaging.test

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
  tests/package/common.sh \
  tests/functional/sanity.py \
  tests/functional/virtexpect.py

DERIVED_KS = data/kickstarts/rootfs.ks \
  data/kickstarts/runtime-layout.ks

PARTIAL_KS = \
  data/kickstarts/partial/repositories.ks \
  data/kickstarts/partial/packages.ks \
  data/kickstarts/partial/header.ks \
  data/kickstarts/partial/post.ks \
  data/kickstarts/partial/minimization.ks

doc_DATA = \
  $(DERIVED_KS)

dist_doc_DATA = \
  data/kickstarts/flatten.py \
  data/kickstarts/template/rootfs.ks \
  data/kickstarts/template/runtime-layout.ks \
  $(PARTIAL_KS) \
  docs/imgbase.asc \
  docs/imgbase.8.asc

man8_MANS = docs/imgbase.8

doc: $(doc_DATA) $(dist_doc_DATA) $(man8-MANS)

check:
	[[ "$(IMAGE)" ]] && $(MAKE) check-functional || :

check-functional: $(IMAGE)
	[[ -f $(IMAGE) ]]
	VIRTEXPECT_IMAGE=$(IMAGE) nosetests -v tests/functional/*.py

boot.iso:
	echo "Please fetch any boot.iso from the desired Fedora release"

doc: $(manpages)

docs/imgbase.8: docs/imgbase.8.asc

rpm:DEF_RELEASE=--define "_release 0.$$(date +%Y%m%d%H%M)git$$(git log -n1 --format=%h)"
rpm: dist
	rpmbuild $(DEF_RELEASE) -ta $(DIST_ARCHIVES)

CLEANFILES = $(DERIVED_KS)

%.ks: template/%.ks $(PARTIAL_KS)
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

%.squash: %.img
	sudo -E virt-sparsify "$<" "$<.sparse"
	mksquashfs "$<.sparse" "$@" -comp xz
	ls -shal "$<" "$<.sparse" "$@"
	sudo rm "$<.sparse"

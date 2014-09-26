
SHELL := /bin/bash

TEST_LOG_DRIVER = env AM_TAP_AWK='$(AWK)' $(SHELL) \
                  $(top_srcdir)/build-aux/tap-driver.sh
TESTS = tests/package/check_python.test tests/package/check_packaging.test

IMAGE = runtime-layout
TESTIMAGE = $(IMAGE).qcow2

hooksdir = $(pkgdatadir)/hooks.d/
pyimagebaseddir = $(pythondir)/$(PACKAGE_NAME)

vpath $(srcdir)

dist_sbin_SCRIPTS = \
  scripts/imgbase

dist_pyimagebased_PYTHON = \
  src/imgbased/*.py

dist_hooks_SCRIPTS = \
  data/hooks/persistence \
  data/hooks/rebase

EXTRA_DIST = \
  README.md \
  LICENSE \
  packaging/rpm/imgbased.spec \
  $(TESTS) \
  tests/package/common.sh \
  tests/runtime/*.py

PARTIAL_KS = $(wildcard data/images/kickstarts/*/*.ks)

dist_doc_DATA = \
  data/images/kickstarts/flatten.py \
  $(PARTIAL_KS) \
  docs/imgbase.asc \
  docs/imgbase.8.asc

man8_MANS = docs/imgbase.8

doc: $(doc_DATA) $(dist_doc_DATA) $(man8-MANS)

#
# Build the test image
#
build: data/images/$(TESTIMAGE)
	mv data/images/$(TESTIMAGE) $(srcdir)

data/images/%.qcow2:
	cd data/images && make run-install DISK_NAME=$(TESTIMAGE) KICKSTART=kickstarts/$(IMAGE).ks


#
# Now some targets to test the installation part
#
rootfs.qcow2:
	make build IMAGE=rootfs

rootfs.tar.xz: rootfs.qcow2
	guestfish -i -a $< tar-out / $@ compress:xz

install: rootfs.tar.xz
	python -m SimpleHTTPServer &
	sed -i "s#@ROOTFS_URL@#http://10.0.2.2:8000/rootfs.tar.xz#" data/images/kickstarts/installation.ks
	qemu-img create -f qcow2 tgt.qcow2 20G
	qemu-kvm \
		-serial stdio \
		-smp 4 -m 2048 \
		-hda tgt.qcow2 \
		-kernel data/images/vmlinuz \
		-initrd data/images/initrd.img \
		-append "inst.ks=http://10.0.2.2:8000/data/images/kickstarts/installation.ks inst.stage2=http://10.0.2.2:8000/ quiet"


#
# Run simple and advanced test
#
check: 
	[[ -f "$(TESTIMAGE)" ]] && $(MAKE) check-runtime || :

#
# Run runtime/functional test on the test image
# Intentioanlly no dependency on build
#
check-runtime: $(TESTIMAGE)
	make -f tests/runtime/Makefile check-local IMAGE=$(abs_srcdir)/$(TESTIMAGE)

#
# Sparsify an image
#
sparse: INTIMAGE = intermediate-$(SRCIMAGE)
sparse: DSTIMAGE = sparse-$(SRCIMAGE)
sparse: $(SRCIMAGE)
	virt-sparsify --compress $(SRCIMAGE) $(INTIMAGE)
	mv -v $(INTIMAGE) $(DSTIMAGE)


doc: $(man8_MANS)

docs/imgbase.8: docs/imgbase.8.asc

rpm:DEF_RELEASE=--define "_release 0.$$(date +%Y%m%d%H%M)git$$(git log -n1 --format=%h)"
rpm: dist
	rpmbuild $(DEF_RELEASE) -ta $(DIST_ARCHIVES)

CLEANFILES = $(DERIVED_KS)

%: %.xml
	xsltproc -o $@ -nonet \
	http://docbook.sourceforge.net/release/xsl/current/manpages/docbook.xsl $<

%.xml: %.asc
	mkdir -p $$(dirname $@)
	asciidoc -d manpage -b docbook -o $@ $<



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
image-build: data/images/$(TESTIMAGE)
	mv data/images/$(TESTIMAGE) $(srcdir)

data/images/%.qcow2:
	cd data/images && make run-install DISK_NAME=$(TESTIMAGE) KICKSTART=kickstarts/$(IMAGE).ks

#
# Now some targets to test the installation part
#
rootfs.qcow2:
	if [[ -e $@ ]]; then echo "rootfs already exists" ; else make image-build IMAGE=rootfs ; fi

rootfs.tar.xz: rootfs.qcow2
	if [[ -e $@ ]]; then echo "Tarball already exists" ; else guestfish -i -a $< tar-out / $@ compress:xz ; fi

image-install: ROOTFS=rootfs.squashfs.img
image-install: ROOTFS_URL=http://10.0.2.2:\$$(PYPORT)/
image-install:
	[[ -f "$(ROOTFS)" ]]
	-rm -f data/images/kickstarts/installation.ks data/images/$(ROOTFS)
	-ln -s $$PWD/$(ROOTFS) data/images/
	make image-build IMAGE=installation SED_KS="s#@ROOTFS_URL@#$(ROOTFS_URL)/$(ROOTFS)#"


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
sparse:
	[[ -f "$(SRCIMAGE)" ]]
	virt-sparsify --compress $(SRCIMAGE) $(INTIMAGE)
	mv -v $(INTIMAGE) $(DSTIMAGE)

#
# Remove the bootloader and label from a disk image
#
strip-disklabel: INTIMAGE = $(SRCIMAGE)-intermediate
strip-disklabel: DSTIMAGE = $(SRCIMAGE)-without-disklabel
strip-disklabel:
	[[ -f "$(SRCIMAGE)" ]]
	set -x ; dd conv=sparse bs=1M skip=1 if="$(SRCIMAGE)" of="$(INTIMAGE)"
	mv -v "$(INTIMAGE)" "$(DSTIMAGE)"

#
# Create a squashfs suitable for dracut and anaconda
#
rootfs.squashfs.img:
	mkdir -p squashfs-root/LiveOS
	-[[ -n "$(SRCDISKIMAGE)" ]] && make strip-disklabel SRCIMAGE=$(SRCDISKIMAGE) DSTIMAGE=squashfs-root/LiveOS/rootfs.img
	-[[ -n "$(SRCIMAGE)" ]] && ln -v $(PWD)/$(SRCIMAGE) squashfs-root/LiveOS/rootfs.img
	[[ -f squashfs-root/LiveOS/rootfs.img ]]
	mksquashfs squashfs-root $@ -comp xz
	rm -rvf squashfs-root

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


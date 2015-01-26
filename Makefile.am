
SHELL := /bin/bash

TEST_LOG_DRIVER = env AM_TAP_AWK='$(AWK)' $(SHELL) \
                  $(top_srcdir)/build-aux/tap-driver.sh
TESTS = tests/package/check_python.test tests/package/check_packaging.test

NAME = rootfs
SQUASHFS=$(NAME).squashfs.img
QCOW = $(NAME).qcow2
QCOW_CHECK = installation.qcow2

hooksdir = $(pkgdatadir)/hooks.d/
pyimagebaseddir = $(pythondir)/$(PACKAGE_NAME)
pyimagebasedpluginsdir = $(pyimagebaseddir)/plugins

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
# and sparsify if possible
#
image-build: data/images/$(QCOW)
	mv data/images/$(QCOW) $(srcdir)
	-virt-sparsify --check-tmpdir continue --compress $(QCOW) $(QCOW).sparse && mv -v $(QCOW).sparse $(QCOW)

data/images/%.qcow2:
	cd data/images && make run-install DISK_NAME=$(QCOW) KICKSTART=kickstarts/$(NAME).ks

#
# Now some targets to test the installation part
#
rootfs.qcow2:
	if [[ -e $@ ]]; then echo "rootfs already exists" ; else make image-build IMAGE=rootfs ; fi

rootfs.raw: rootfs.qcow2
	if [[ -e $@ ]]; then echo "rootfs already exists" ; else qemu-img convert -p -S 1M -O raw $< $@; fi

rootfs.squashfs.img: rootfs.raw
	mkdir -p squashfs-root/LiveOS
#	Check if it's a disk image, then we need to remove the label to get the partition, assumption: On partition
#	FIXME The size of the mbr/label is hardcoded, works by removing the label from the disk image
	-[[ $$(file $<) =~ "boot sector" ]] && dd conv=sparse bs=1M skip=1 if=$< of=squashfs-root/LiveOS/rootfs.img
#	If the image is already afilesystem, take it directly
	-[[ $$(file $<) =~ "filesystem" ]] && ln -v $(PWD)/$(SRCIMAGE) squashfs-root/LiveOS/rootfs.img
	[[ -f squashfs-root/LiveOS/rootfs.img ]]
	mksquashfs squashfs-root $@ -comp xz
	rm -rvf squashfs-root

rootfs.tar.xz: rootfs.qcow2
	if [[ -e $@ ]]; then echo "Tarball already exists" ; else guestfish -i -a $< tar-out / $@ compress:xz ; fi

image-install: SQUASHFS_URL=http://10.0.2.2:\$$(PYPORT)/
image-install: $(SQUASHFS)
	[[ -f "$(SQUASHFS)" ]]
	-rm -f data/images/kickstarts/installation.ks data/images/$(SQUASHFS)
	-ln -s $$PWD/$(SQUASHFS) data/images/
	make image-build NAME=installation SED_KS="s#@ROOTFS_URL@#$(SQUASHFS_URL)/$(SQUASHFS)#"

verrel: TYPE=rootfs
verrel: NAME=FedoraNodeNext
verrel: VENDOR=org.ovirt.node
verrel: ARCH=x86_64
verrel: VERSION=$$(date +%Y%m%d)$(EXTRA_RELEASE)
verrel:
	@echo $(TYPE):$(NAME):$(VENDOR):$(ARCH):$(VERSION)


#
# Run simple and advanced test
#
check:
	[[ -f "$(QCOW_CHECK)" ]] && $(MAKE) check-runtime || :

#
# Run runtime/functional test on the test image
# Intentioanlly no dependency on build
#
check-runtime: $(QCOW_CHECK)
	make -f tests/runtime/Makefile check-local IMAGE=$(QCOW_CHECK)

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


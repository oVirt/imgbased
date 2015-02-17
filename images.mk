#
# This makefile includes functionality related to building and
# testing the images which can be created usign the kickstart
# files
#

KICKSTARTS=$(wildcard data/images/kickstarts/*/*.ks)
.SECONDARY: rootfs.qcow2

image-build: rootfs.qcow2

%.qcow2: $(KICKSTARTS)
	make -C data/images kickstarts/$*.ks
	mv -vf data/images/kickstarts/$*.ks
	make -f tools/build.mk $@
	-virt-sparsify --check-tmpdir continue --compress $@ $@.sparse && mv -v $@.sparse $@

%.squashfs.img: %.qcow2
	 make -f tools/build.mk $@
	unsquashfs -ll $@

image-install:
	[[ -f rootfs.squashfs.img ]]
	-rm -f data/images/kickstarts/installation.ks
	$(MAKE) -C data/images kickstarts/installation.ks
	mv -vf data/images/kickstarts/installation.ks .
	sed -i "s#@ROOTFS_URL@#@HOST_HTTP@/rootfs.squashfs.img#" installation.ks
	$(MAKE) -f tools/build.mk installation.qcow2

verrel:
	@bash tools/image-verrel rootfs NodeNext org.ovirt.node

check: QCOW_CHECK=installation.qcow2
check:
	[[ -f "$(QCOW_CHECK)" ]] && make -f tests/runtime/Makefile check-local IMAGE=$(QCOW_CHECK) || :


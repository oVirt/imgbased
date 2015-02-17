#
# This makefile includes functionality related to building and
# testing the images which can be created usign the kickstart
# files
#

KICKSTARTS=$(wildcard data/kickstarts/*/*.ks)
CLEANFILES+=$(wildcard *.qcow2) $(wildcard *.ks)
.SECONDARY: rootfs.qcow2


image-build: rootfs.qcow2

image-install: SQUASHFS_URL="@HOST_HTTP@/rootfs.squashfs.img"
image-install: installation.ks
	[[ -f rootfs.squashfs.img ]]
	$(MAKE) -C data/kickstarts installation.ks
	mv -vf data/kickstarts/installation.ks .
	sed -i "s#@ROOTFS_URL@#$(SQUASHFS_URL)#" installation.ks
	$(MAKE) -f tools/build.mk installation.qcow2

verrel:
	@bash tools/image-verrel rootfs NodeNext org.ovirt.node

check: QCOW_CHECK=installation.qcow2
check:
	[[ -f "$(QCOW_CHECK)" ]] && make -f tests/runtime/Makefile check-local IMAGE=$(QCOW_CHECK) || :


%.ks:
	-rm -f data/kickstarts/installation.ks
	make -C data/kickstarts $@
	mv -vf data/kickstarts/$@ $@

%.qcow2: %.ks
	make -f tools/build.mk $@
	-virt-sparsify --check-tmpdir continue --compress $@ $@.sparse && mv -v $@.sparse $@

%.squashfs.img: %.qcow2
	 make -f tools/build.mk $@
	unsquashfs -ll $@


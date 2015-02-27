#
# This makefile includes functionality related to building and
# testing the images which can be created usign the kickstart
# files
#

KICKSTARTS=$(wildcard data/kickstarts/*/*.ks)
CLEANFILES+=$(wildcard *.qcow2) $(wildcard *.ks) vmlinuz initrd.img squashfs.img
.SECONDARY: rootfs.qcow2 rootfs.ks

# FIXME Stick to Fedora until this is solved: http://bugs.centos.org/view.php?id=8239
DISTRO=fedora
RELEASEVER=21

image-build: rootfs.qcow2

image-install: SQUASHFS_URL="@HOST_HTTP@/rootfs.squashfs.img"
image-install: installation.ks
	[[ -f rootfs.squashfs.img ]]
	$(MAKE) -C data/kickstarts installation.ks
	mv -vf data/kickstarts/installation.ks .
	sed -i "s#@ROOTFS_URL@#$(SQUASHFS_URL)#" installation.ks
	$(MAKE) -f image-tools/build.mk DISTRO=$(DISTRO) RELEASEVER=$(RELEASEVER) DISK_SIZE=$$(( 10 * 1024 )) SPARSE= installation.qcow2

verrel:
	@bash image-tools/image-verrel rootfs NodeNext org.ovirt.node

check: QCOW_CHECK=installation.qcow2
check:
	[[ -f "$(QCOW_CHECK)" ]] && make -f tests/runtime/Makefile check-local IMAGE=$(QCOW_CHECK) || :


%.ks:
	-rm -f data/kickstarts/installation.ks
	$(MAKE) -C data/kickstarts DISTRO=$(DISTRO) RELEASEVER=$(RELEASEVER) $@
	mv -vf data/kickstarts/$@ $@

%.qcow2: %.ks
	make -f image-tools/build.mk DISTRO=$(DISTRO) RELEASEVER=$(RELEASEVER) $@

%.squashfs.img: %.qcow2
	 make -f image-tools/build.mk $@
	unsquashfs -ll $@

%-manifest-rpm: %.qcow2
	 make -f image-tools/build.mk $@

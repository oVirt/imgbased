#
# This makefile includes functionality related to building and
# testing the images which can be created usign the kickstart
# files
#

CLEANFILES+=$(wildcard *.qcow2) $(wildcard *.ks) vmlinuz initrd.img squashfs.img
.SECONDARY: rootfs.qcow2 rootfs.ks

# FIXME Stick to Fedora until this is solved: http://bugs.centos.org/view.php?id=8239
DISTRO=fedora
RELEASEVER=22

image-build: rootfs.qcow2

image-install: SQUASHFS_URL="@HOST_HTTP@/rootfs.squashfs.img"
image-install: data/ks/auto-installation-testing.ks.in
	[[ -f rootfs.squashfs.img ]]
	sed "s#@ROOTFS_URL@#$(SQUASHFS_URL)#" data/ks/auto-installation-testing.ks.in > auto-installation-testing.ks
	$(MAKE) -f image-tools/build.mk DISTRO=$(DISTRO) RELEASEVER=$(RELEASEVER) DISK_SIZE=$$(( 10 * 1024 )) SPARSE= auto-installation-testing.qcow2

verrel:
	@bash image-tools/image-verrel rootfs ImgbaseAppliance com.github.imgbased

check: QCOW_CHECK=auto-installation-testing.qcow2
check:
	[[ -f "$(QCOW_CHECK)" ]] && make -f tests/runtime/Makefile check-local IMAGE=$(QCOW_CHECK) || :

%.qcow2: data/ks/%.ks
	cp $< .
	make -f image-tools/build.mk DISTRO=$(DISTRO) RELEASEVER=$(RELEASEVER) $@

%.squashfs.img: %.qcow2
	 make -f image-tools/build.mk $@
	unsquashfs -ll $@

%-manifest-rpm: %.qcow2
	 make -f image-tools/build.mk $@

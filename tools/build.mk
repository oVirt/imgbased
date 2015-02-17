#
# This makefile includes functionality related to building and
# testing the images which can be created usign the kickstart
# files
#
mkfile_dir := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

DISTRO=fedora
RELEASEVER=21

noop:
	@echo Please select a specific target
	@echo make rootfs.qcow2
	@echo This expects rootfs.ks to exist

%.qcow2: %.ks
	bash $(mkfile_dir)/anaconda_install $(DISTRO) $(RELEASEVER) $< $@

%.raw: %.qcow2
	qemu-img convert -p -S 1M -O raw $< $@

%.squashfs.img: %.raw
	bash $(mkfile_dir)/image_to_squashfs $< $@

%.tar.xz: %.qcow2
	guestfish -i -a $< tar-out / $@ compress:xz


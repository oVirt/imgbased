#
# This makefile includes functionality related to building and
# testing the images which can be created usign the kickstart
# files
#

NAME = rootfs
SQUASHFS=$(NAME).squashfs.img
QCOW = $(NAME).qcow2
QCOW_CHECK = installation.qcow2

.SECONDARY : rootfs.qcow2

#
# Build the test image
# and sparsify if possible
#
image-build: $(QCOW)

clean-build:
	cd data/images && make clean

$(QCOW): $(PARTIAL_KS)
	cd data/images && make run-install DISK_NAME=$(QCOW) KICKSTART=kickstarts/$(NAME).ks
	mv -v data/images/$(QCOW) $(srcdir)
	-virt-sparsify --check-tmpdir continue --compress $(QCOW) $(QCOW).sparse && mv -v $(QCOW).sparse $(QCOW)

#
# Now some targets to test the installation part
#
rootfs.raw: rootfs.qcow2
	qemu-img convert -p -S 1M -O raw $< $@

rootfs.squashfs.img: rootfs.raw
	mkdir -p squashfs-root/LiveOS
#	Check if it's a disk image, then we need to remove the label to get the partition, assumption: On partition
#	FIXME The size of the mbr/label is hardcoded, works by removing the label from the disk image
	-[[ $$(file $<) =~ "boot sector" ]] && dd conv=sparse bs=1M skip=1 if=$< of=squashfs-root/LiveOS/rootfs.img
#	If the image is already afilesystem, take it directly
	-[[ $$(file $<) =~ "filesystem" ]] && ln -v $(PWD)/$(SRCIMAGE) squashfs-root/LiveOS/rootfs.img
	[[ -f squashfs-root/LiveOS/rootfs.img ]]
	mksquashfs squashfs-root $@ -comp xz -noappend
	rm -rvf squashfs-root

rootfs.tar.xz: rootfs.qcow2
	if [[ -e $@ ]]; then echo "Tarball already exists" ; else guestfish -i -a $< tar-out / $@ compress:xz ; fi

image-install: SQUASHFS_URL=http://10.0.2.2:\$$(PYPORT)/
image-install: $(SQUASHFS)
	[[ -f "$(SQUASHFS)" ]]
	-rm -f data/images/kickstarts/installation.ks data/images/$(SQUASHFS)
	-ln -s $$PWD/$(SQUASHFS) data/images/
	$(MAKE) image-build NAME=installation SED_KS="s#@ROOTFS_URL@#$(SQUASHFS_URL)/$(SQUASHFS)#"

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



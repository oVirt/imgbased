
#
# How to use
# $ export ALL_PROXY=10.0.2.2:3128
# $ make run-install
#

KICKSTART ?= data/kickstarts/runtime-layout.ks

DISK_NAME ?= hda.qcow2
DISK_SIZE ?= 10G

VM_RAM ?= 2048
VM_SMP ?= 4

QEMU ?= qemu-kvm
CURL ?= curl -L -O

FEDORA_RELEASEVER ?= 20
FEDORA_URL ?= http://download.fedoraproject.org/pub/fedora/linux/releases/$(FEDORA_RELEASEVER)/Fedora/x86_64/os/

SHELL = /bin/bash


.INTERMEDIATE: spawned_pids

vmlinuz:
	$(CURL) $(FEDORA_URL)/isolinux/vmlinuz

initrd.img:
	$(CURL) $(FEDORA_URL)/isolinux/initrd.img

squashfs.img:
	$(CURL) $(FEDORA_URL)/LiveOS/squashfs.img

run-install: vmlinuz initrd.img squashfs.img
	python -m SimpleHTTPServer 8042 & echo $$! > spawned_pids
	qemu-img create -f qcow2 $(DISK_NAME) $(DISK_SIZE)
	$(QEMU) -vnc 0.0.0.0:7 -smp $(VM_SMP) -m $(VM_RAM) -hda $(DISK_NAME) -kernel vmlinuz -initrd initrd.img -append "inst.repo=$(FEDORA_URL) inst.ks=http://10.0.2.2:8042/$(KICKSTART) root=live:http://10.0.2.2:8042/squashfs.img" ; \
	kill $$(cat spawned_pids)

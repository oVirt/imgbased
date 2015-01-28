
#
# How to use
# $ make run-install
#
# https://git.fedorahosted.org/cgit/anaconda.git/tree/docs/boot-options.txt
SHELL = /bin/bash

KICKSTART = kickstarts/runtime-layout.ks

DISK_NAME = hda.qcow2
DISK_SIZE = 10G

VM_RAM = 2048
VM_SMP = 4

QEMU = qemu-kvm
QEMU_APPEND =
CURL = curl -L -O --fail

FEDORA_URL=https://alt.fedoraproject.org/pub/alt/stage/current/Server/x86_64/os/
RELEASEVER = 21

MIRRORCURL = bash -c "curl --fail -s 'https://mirrors.fedoraproject.org/mirrorlist?repo=fedora-install-$(RELEASEVER)&arch=x86_64' | sed -n 's/Everything/Fedora/ ; /^ht/ p'  | while read BURL; do URL=\$$BURL\$$0 ; echo Using \$$URL ; curl --fail -L -O \$$URL && break ; done ; test -f \$$(basename \$$0)"


.INTERMEDIATE: spawned_pids

vmlinuz:
	$(MIRRORCURL) isolinux/vmlinuz

initrd.img:
	$(MIRRORCURL) isolinux/initrd.img

squashfs.img:
	$(MIRRORCURL) LiveOS/squashfs.img


.PHONY: .treeinfo
.treeinfo:
	$(MIRRORCURL) $@ > $@
	echo Adjusting squashfs image path, so anaconda finds it
	# Anaconda uses the .treeinfo file to find stuff
	sed -i \
		"s/=.*squashfs\.img/= squashfs.img/" \
		$@
	cat $@

run-install: PYPORT:=$(shell echo $$(( 50000 + $$RANDOM % 15000 )) )
run-install: VNCPORT:=$(shell echo $$(( $$RANDOM % 1000 )) )
run-install: .treeinfo vmlinuz initrd.img squashfs.img $(KICKSTART)
	python -m SimpleHTTPServer $(PYPORT) & echo $$! > spawned_pids
	sed -i -e "$(SED_KS)" $(KICKSTART)
	qemu-img create -f qcow2 $(DISK_NAME) $(DISK_SIZE)
	$(QEMU) \
		-vnc 0.0.0.0:$(VNCPORT) \
		-serial stdio \
		-smp $(VM_SMP) -m $(VM_RAM) \
		-hda $(DISK_NAME) \
		-kernel vmlinuz \
		-initrd initrd.img \
		-device virtio-serial -chardev file,id=logfile,path=anaconda.log -device virtserialport,name=org.fedoraproject.anaconda.log.0,chardev=logfile \
		-append "console=ttyS0 inst.ks=http://10.0.2.2:$(PYPORT)/$(KICKSTART) inst.stage2=http://10.0.2.2:$(PYPORT)/ quiet cmdline inst.virtiolog $(QEMU_APPEND)" ; \
	kill $$(cat spawned_pids)

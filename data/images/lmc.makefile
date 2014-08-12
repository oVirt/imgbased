
SUDO ?= sudo -E
LMC ?= livemedia-creator
CURL ?= curl

VM_CPUS ?= 4
VM_RAM ?= 4096

# Units can be used here
VM_GROWSIZE ?= 10GB

ARCH := x86_64
RELEASEVER := 20
BOOTISO ?= Fedora-$(RELEASEVER)-$(ARCH)-netinst.iso

# LMC options
TMPDIR := result-$(shell date +%Y%m%d%H%M%S)
LMC_ARGS = --ram=$(VM_RAM) --vcpus=$(VM_CPUS)
LMC_ARGS += --tmp="$(TMPDIR)"


$(BOOTISO):
	$(CURL) -L -O http://download.fedoraproject.org/pub/fedora/linux/releases/$(RELEASEVER)/Fedora/$(ARCH)/iso/$(BOOTISO)


%.raw: data/kickstarts/%.ks $(BOOTISO)
	mkdir $(TMPDIR)
	chmod a+rwX $(TMPDIR)
	$(SUDO) $(LMC) $(LMC_ARGS) --make-disk \
          --ks "$<" \
          --iso $(BOOTISO) \
          --image-name "$@"
	mv -v $(TMPDIR)/"$@" .

%.qcow2: %.raw
	$(SUDO) virt-sparsify --compress --convert qcow2 "$<" "$@"
# FIXME selinux relable must hapen before init-label, before we cna enable
# relable
# The options also need to be given explicitly, because some others destroy the firstboot/initial-setup
	$(SUDO) virt-sysprep --no-selinux-relabel --add "$@" --enable abrt-data,bash-history,blkid-tab,ca-certificates,crash-data,cron-spool,dhcp-client-state,dovecot-data,hostname,lvm-uuids,machine-id,mail-spool,net-hostname,net-hwaddr,pacct-log,package-manager-cache,random-seed,smolt-uuid,ssh-hostkeys,ssh-userdir,sssd-db-log,udev-persistent-net,utmp,yum-uuid
	$(SUDO) qemu-img resize "$@" $(VM_GROWSIZE)

%.fs: data/kickstarts/%.ks
	$(SUDO) $(LMC) $(LMC_ARGS) --make-fsimage \
          --ks "$<" \
          --iso $(BOOTISO) --vcpus 4 \
          --image-name "$@"
	sudo mv "/var/tmp/$@" .

%.iso: %.fs
	$(SUDO) $(LMC) $(LMC_ARGS) --make-iso \
          --fs-image "$<" \
          --image-name "$@"

%.squash: %.img
	mksquashfs "$<.sparse" "$@" -comp xz
	ls -shal "$<" "$<.sparse" "$@"
	$(SUDO) rm "$<.sparse"

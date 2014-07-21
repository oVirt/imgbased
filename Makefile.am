
SHELL := /bin/bash

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


TEST_LOG_DRIVER = env AM_TAP_AWK='$(AWK)' $(SHELL) \
                  $(top_srcdir)/build-aux/tap-driver.sh
TESTS = tests/package/check_python.test tests/package/check_packaging.test

hooksdir = $(pkgdatadir)/hooks.d/
pyimagebaseddir = $(pythondir)/$(PACKAGE_NAME)

vpath $(srcdir)

dist_sbin_SCRIPTS = \
  data/imgbase

dist_pyimagebased_PYTHON = \
  src/__init__.py \
  src/imgbase.py

dist_hooks_SCRIPTS = \
  data/hooks/persistence \
  data/hooks/rebase

EXTRA_DIST = \
  README.md \
  imgbased.spec \
  $(TESTS) \
  tests/package/common.sh \
  tests/functional/sanity.py \
  tests/functional/virtexpect.py

DERIVED_KS = data/kickstarts/rootfs.ks \
  data/kickstarts/runtime-layout.ks

PARTIAL_KS = \
  data/kickstarts/partial/repositories.ks \
  data/kickstarts/partial/packages.ks \
  data/kickstarts/partial/header.ks \
  data/kickstarts/partial/post.ks \
  data/kickstarts/partial/minimization.ks

doc_DATA = \
  $(DERIVED_KS)

dist_doc_DATA = \
  data/kickstarts/flatten.py \
  data/kickstarts/template/rootfs.ks \
  data/kickstarts/template/runtime-layout.ks \
  $(PARTIAL_KS) \
  docs/imgbase.asc \
  docs/imgbase.8.asc

man8_MANS = docs/imgbase.8

doc: $(doc_DATA) $(dist_doc_DATA) $(man8-MANS)

check:
	[[ "$(IMAGE)" ]] && $(MAKE) check-functional || :

check-functional:
	[[ -f $(IMAGE) ]]
	VIRTEXPECT_IMAGE=$(IMAGE) nosetests -v $(srcdir)/tests/functional/*.py

doc: $(man8_MANS)

docs/imgbase.8: docs/imgbase.8.asc

rpm:DEF_RELEASE=--define "_release 0.$$(date +%Y%m%d%H%M)git$$(git log -n1 --format=%h)"
rpm: dist
	rpmbuild $(DEF_RELEASE) -ta $(DIST_ARCHIVES)

CLEANFILES = $(DERIVED_KS)

data/kickstarts/%.ks: data/kickstarts/template/%.ks $(PARTIAL_KS)
	mkdir -p $$(dirname "$@")
	$(srcdir)/data/kickstarts/flatten.py "$<" > "$@"

%: %.xml
	xsltproc -o $@ -nonet \
	http://docbook.sourceforge.net/release/xsl/current/manpages/docbook.xsl $<

%.xml: %.asc
	mkdir -p $$(dirname $@)
	asciidoc -d manpage -b docbook -o $@ $<

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

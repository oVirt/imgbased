
DISTRO=fedora
PARTIAL_KS=$(wildcard kickstarts/partial/*.ks kickstarts/baseos/*.ks)

all: run-install
	echo Done

sparsify:
	virt-sparsify --compress --convert qcow2 "$<" "$@"

grow:
	qemu-img resize "$@" $(VM_GROWSIZE)

kickstarts/%.ks: kickstarts/template/%.ks $(PARTIAL_KS)
	echo partials: $(PARTIAL_KS)
	echo distro: $(DISTRO)
	mkdir -p $$(dirname "$@")
	ln -vfs kickstarts/baseos/$(DISTRO).ks kickstarts/partial/os.ks
	kickstarts/flatten.py "$<" > "$@"
	[[ -n "$$http_proxy" ]] && sed -i "s/^\(url\|repo\) /\1 --proxy=$$http_proxy /" "$@" || :

include poor-mans-lmc.makefile

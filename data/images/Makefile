
PARTIAL_KS=$(wildcard kickstarts/partial/*.ks)

all: run-install
	echo Done

sparsify:
	virt-sparsify --compress --convert qcow2 "$<" "$@"

grow:
	qemu-img resize "$@" $(VM_GROWSIZE)

kickstarts/%.ks: kickstarts/template/%.ks $(PARTIAL_KS)
	echo partials: $(PARTIAL_KS)
	mkdir -p $$(dirname "$@")
	kickstarts/flatten.py "$<" > "$@"
	[[ -n "$$http_proxy" ]] && sed -i "s/^\(url\|repo\) /\1 --proxy=$$http_proxy /" "$@" || :

include poor-mans-lmc.makefile

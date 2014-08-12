
all: run-install
	echo Done

sparsify:
	virt-sparsify --compress --convert qcow2 "$<" "$@"

grow:
	qemu-img resize "$@" $(VM_GROWSIZE)

kickstarts/%.ks: kickstarts/template/%.ks $(PARTIAL_KS)
	mkdir -p $$(dirname "$@")
	kickstarts/flatten.py "$<" > "$@"

include poor-mans-lmc.makefile

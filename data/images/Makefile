
DISTRO=fedora
PARTIAL_KS=$(wildcard kickstarts/partial/*.ks kickstarts/baseos/*.ks)

dummy:
	@echo Nothing to do

sparsify:
	virt-sparsify --compress --convert qcow2 "$<" "$@"

kickstarts/%.ks: kickstarts/template/%.ks $(PARTIAL_KS)
	@mkdir -p $$(dirname "$@")
	cat "kickstarts/baseos/$(DISTRO).ks" >> "$@"
	kickstarts/flatten.py "$<" >> "$@"
	[[ -n "$$http_proxy" ]] && sed -i "s/^\(url\|repo\) /\1 --proxy=$$http_proxy /" "$@" || :

CLEANFILES+=$(wildcard kickstarts/*.ks)

include poor-mans-lmc.makefile

clean:
	-rm -vf $(CLEANFILES)

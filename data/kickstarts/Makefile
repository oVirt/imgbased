
DISTRO=fedora
.PHONY: $(wildcard *.ks)

dummy:
	@echo Nothing to do

sparsify:
	virt-sparsify --compress --convert qcow2 "$<" "$@"

%.ks: template/%.ks
	@mkdir -p $$(dirname "$@")
	python flatten.py "$<" > "$@"
	# Add platform only if no liveimg source is given
	grep liveimg $@ || cat "platform/$(DISTRO).ks" >> "$@"
	[[ -n "$$http_proxy" ]] && sed -i "s/^\(url\|repo\) /\1 --proxy=$$http_proxy /" "$@" || :

CLEANFILES+=$(wildcard *.ks)

clean:
	-rm -vf $(CLEANFILES)

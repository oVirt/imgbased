
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

CLEANFILES+=$(wildcard *.ks)

clean:
	-rm -vf $(CLEANFILES)

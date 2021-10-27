installdeps:
	dnf -y install git autoconf automake make asciidoc

srpm: installdeps
	$(eval SUFFIX=$(shell sh -c " echo '0.0.$$(date -u +%Y%m%d%H%M%S).git$$(git rev-parse --short HEAD)'"))
	mkdir -p tmp.repos/SOURCES
	./autogen.sh
	make dist
	rpmbuild \
		-D "_topdir tmp.repos" \
		-D "_release ${SUFFIX}" \
		-ts ./*.tar.xz
	cp tmp.repos/SRPMS/*.src.rpm $(outdir)

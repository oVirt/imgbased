.PHONY: installdeps srpm

installdeps:
	dnf -y install git autoconf automake make asciidoc

srpm: installdeps
	# $(eval SUFFIX=$(shell sh -c " echo '0.0.$$(date -u +%Y%m%d%H%M%S).git$$(git rev-parse --short HEAD)'"))
	# changing the spec file as passing -D won't preserve the suffix when rebuilding in mock
	# sed "s:%{?_release}:${SUFFIX}:" -i packaging/rpm/imgbased.spec.in
	# sed "s/%{?\!_release:1}//" -i packaging/rpm/imgbased.spec.in
	mkdir -p tmp.repos/SOURCES
	./autogen.sh
	make dist
	rpmbuild \
		-D "_topdir tmp.repos" \
		-ts ./*.tar.xz
	cp tmp.repos/SRPMS/*.src.rpm $(outdir)

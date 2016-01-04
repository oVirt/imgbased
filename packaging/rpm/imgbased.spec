# FIXME Follow https://fedoraproject.org/wiki/Packaging:Python
%define is_el7 %(test 0%{?centos} -eq 07 || test 0%{?rhel} -eq 07 && echo 1 || echo 0)

Name:           imgbased
Version:        0.3
Release:        %{?_release}%{?!_release:0.1}%{?dist}
Summary:        Tools to work with an image based rootfs

License:        GPLv2+
URL:            https://www.github.com/fabiand/imgbased
Source0:        %{name}-%{version}.tar.xz

BuildArch:      noarch

BuildRequires:       make
BuildRequires:       automake autoconf
BuildRequires:       rpm-build
BuildRequires:       git
BuildRequires:       asciidoc

BuildRequires:       python-devel python-six
BuildRequires:       pylint python-pep8 pyflakes python-nose

%if 0%{?is_el7}
BuildRequires:       python-six
%else
Recommends:          systemd-python3
BuildRequires:       python3-six
%endif

Requires:       lvm2
Requires:       util-linux
Requires:       augeas
Requires:       rsync


%description
This tool enforces a special usage pattern for LVM.
Basically this is about having read-only bases and writable
layers atop.


%prep
%setup -q


%build
%configure
make %{?_smp_mflags}


%install
%make_install


%files
%doc README.md LICENSE
%{_sbindir}/imgbase
%{_datadir}/%{name}/hooks.d/
%{python_sitelib}/%{name}/
%{_mandir}/man8/imgbase.8*
/%{_docdir}/%{name}/*.asc


%changelog
* Wed Apr 02 2014 Fabian Deutsch <fabiand@fedoraproject.org> - 0.1-0.1
- Initial package


Name:           imgbased
Version:        0.1
Release:        %{?_release}%{?!_release:0.1}%{?dist}
Summary:        Tools to work with an image based rootfs

License:        GPLv2+
URL:            https://www.github.com/fabiand/imgbased
Source0:        %{name}-%{version}.tar.xz

BuildArch:      noarch

BuildRequires:       make
BuildRequires:       automake autoconf
BuildRequires:       asciidoc
BuildRequires:       python
BuildRequires:       pylint python-pep8 pyflakes


%description
This tool enforces a special usage pattern for LVM.
Basically this is about having read-only bases and writable
layers atop.


%package kickstarts
Summary:        Kickstarts to create some related images
Group:          Applications/System
BuildRequires:  pykickstart
Requires:       lorax


%description kickstarts
This is a collection of kickstarts to create images to test
the tool.
And also provides other kickstarts for reference.


%prep
%setup -q


%build
%configure
make %{?_smp_mflags}


%install
%make_install


%check
%{__make} check TESTS="tests/package/check_python.test"


%files
%doc README.md
%{_sbindir}/imgbase
%{_datadir}/%{name}/hooks.d/
%{python2_sitelib}/%{name}/
%{_mandir}/man8/imgbase.8*


%files kickstarts
%{_docdir}/%{name}


%changelog
* Wed Apr 02 2014 Fabian Deutsch <fabiand@fedoraproject.org> - 0.1-0.1
- Initial package

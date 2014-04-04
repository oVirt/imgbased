Name:           imgbased
Version:        0.1
Release:        0.1%{?dist}
Summary:        Tools to work with an image based rootfs

License:        GPLv2+
URL:            https://www.github.com/fabiand/imgbased
Source0:        %{name}-%{version}.tar.xz

BuildArch:      noarch

BuildRequires:       make
BuildRequires:       automake autoconf
BuildRequires:       python


%description
TBD


%package kickstarts
Summary:        Kickstarts to create some related images
Group:          Applications/System
BuildRequires:  pykickstart
Requires:       lorax


%description kickstarts
TBD


%prep
%setup -q


%build
%configure
make %{?_smp_mflags}


%install
%make_install


%check
%{__make} check TESTS="tests/check_python.test"


%files
%doc README.md
%{_sbindir}/imgbase
%{_prefix}/lib/%{name}/hooks.d/
%{python2_sitelib}/%{name}/


%files kickstarts
%{_docdir}/%{name}


%changelog
* Wed Apr 02 2014 Fabian Deutsch <fabiand@fedoraproject.org> - 0.1-0.1
- Initial package

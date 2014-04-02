Name:           imgbased
Version:        0.1
Release:        0.1%{?dist}
Summary:        Tools to work with an image based rootfs

License:        GPLv2+
URL:            https://www.github.com/fabiand/imgbased
Source0:        

#BuildRequires:  
#Requires:       


%description


%prep
%setup -q


%build
%configure
make %{?_smp_mflags}


%install
%{buildroot}
%make_install


%files
%doc README.md



%changelog

Name:       imgbased-persist
Version:    1
Release:    1%{?dist}
Summary:    1
License:    GPLv2+
BuildArch:  noarch

%description
Dummy rpm to check persisting rpms with imgbased on ovirt-node-ng

%prep
echo "Nothing to see here" >  empty.file

%install
install -Dm 666 empty.file %{buildroot}/var/lib/%{name}/empty.file

%files
/var/lib/%{name}/empty.file


#
# Cleanup some stuff using image-minimizer
#
%post --nochroot --interpreter image-minimizer

drop /usr/share/zoneinfo
keep /usr/share/zoneinfo/UTC

drop /usr/share/awk
drop /usr/share/vim
drop /usr/src

# glibc-common locales
drop /usr/lib/locale
keep /usr/lib/locale/locale-archive

# docs
drop /usr/share/doc
drop /usr/share/locale/
keep /usr/share/locale/en_US
drop /usr/share/man

# yum
drop /var/log/yum.log
drop /var/lib/yum/*
drop /var/cache/yum/*
drop /root/install.*
drop /root/anaconda.*
drop /var/log/anaconda*
%end


#
# Remove some stuff using image-minimizer
#
%post --nochroot --interpreter image-minimizer

# kernel modules minimization
drop /lib/modules/*/kernel/sound
drop /lib/modules/*/kernel/drivers/media
drop /lib/modules/*/kernel/net/wireless

drop /usr/share/zoneinfo
keep /usr/share/zoneinfo/UTC

drop /usr/share/awk
drop /usr/share/vim
drop /usr/src

# glibc-common locales
drop /usr/lib/locale
keep /usr/lib/locale/locale-archive
keep /usr/lib/locale/usr/share/locale/en_US

# docs
drop /usr/share/doc
drop /usr/share/locale/
keep /usr/share/locale/en_US
keep /usr/share/locale/zh_CN
drop /usr/share/man

# yum
drop /var/log/yum.log
drop /var/lib/yum/*
drop /var/cache/yum/*
drop /root/install.*
drop /root/anaconda.*
drop /var/log/anaconda*
%end

#
# Just run depmod because we messed with kernel modules
#
%post
depmod -a
%end

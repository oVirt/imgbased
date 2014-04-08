
#
# Remove some stuff using image-minimizer
#
%post --nochroot --interpreter image-minimizer

droprpm system-config-*
keeprpm system-config-keyboard-base

droprpm gamin
droprpm pm-utils
droprpm usermode
droprpm vbetool
droprpm ConsoleKit
keeprpm ConsoleKit-libs
droprpm linux-atm-libs
droprpm mtools
droprpm syslinux
droprpm wireless-tools
droprpm radeontool
droprpm gnupg2

droprpm fakechroot
droprpm fakechroot-libs
droprpm fakeroot
droprpm fakeroot-libs
droprpm febootstrap

droprpm exim
droprpm perl*
keeprpm perl-libs
droprpm postfix
droprpm mysql*

droprpm sysklogd
# kernel modules minimization

# network
drop /lib/modules/*/kernel/sound
drop /lib/modules/*/kernel/drivers/media
drop /lib/modules/*/kernel/net/wireless

drop /usr/share/zoneinfo
keep /usr/share/zoneinfo/UTC

drop /etc/alsa
drop /usr/share/alsa
drop /usr/share/awk
drop /usr/share/vim
drop /usr/share/anaconda
drop /usr/share/backgrounds
drop /usr/share/wallpapers
drop /usr/share/kde-settings
drop /usr/share/gnome-background-properties
drop /usr/share/setuptool
drop /usr/share/hwdata/MonitorsDB
drop /usr/share/hwdata/oui.txt
drop /usr/share/hwdata/videoaliases
drop /usr/share/hwdata/videodrivers
drop /usr/share/firstboot
drop /usr/share/lua
drop /usr/share/kde4
drop /usr/share/pixmaps
drop /usr/share/icons
drop /usr/share/fedora-release
drop /usr/share/tabset
drop /usr/share/tc
drop /usr/share/emacs
drop /usr/share/info
drop /usr/src
drop /usr/etc
drop /usr/games
drop /usr/include
keep /usr/include/python2.*
drop /usr/local
drop /usr/sbin/dell*
keep /usr/sbin/build-locale-archive
drop /usr/sbin/glibc_post_upgrade.*
drop /usr/lib*/tc
drop /usr/lib*/tls
drop /usr/lib*/sse2
drop /usr/lib*/pkgconfig
drop /usr/lib*/nss
drop /usr/lib*/games
drop /usr/lib*/alsa-lib
drop /usr/lib*/krb5
drop /usr/lib*/hal
drop /usr/lib*/gio

# glibc-common locales
drop /usr/lib/locale
keep /usr/lib/locale/locale-archive
keep /usr/lib/locale/usr/share/locale/en_US

# pango
drop /usr/lib*/pango
drop /usr/lib*/libthai*
drop /usr/share/libthai
drop /usr/bin/pango*

# docs
drop /usr/share/omf
drop /usr/share/gnome
drop /usr/share/doc
drop /usr/share/locale/
keep /usr/share/locale/en_US
keep /usr/share/locale/zh_CN
drop /usr/share/man
drop /usr/share/X11
drop /usr/share/i18n
drop /var/lib/builder
drop /usr/sbin/*-channel

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

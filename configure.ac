AC_INIT([imgbased], [0.2], [fabiand@fedoraproject.org])

AC_PREFIX_DEFAULT([/usr])
AC_CONFIG_AUX_DIR([build-aux])
AC_REQUIRE_AUX_FILE([tap-driver.sh])
AC_PROG_AWK

AM_INIT_AUTOMAKE([foreign 1.11 -Wall -Wno-portability silent-rules tar-pax no-dist-gzip dist-xz subdir-objects])
AM_MAINTAINER_MODE([enable])
AM_SILENT_RULES([yes])

AC_SUBST([FEDORA],[[`rpm --eval '%{fedora}'|sed 's/[^0-9]//g'`]])
AC_SUBST([RHEL], [[`rpm --eval '%{rhel}'|sed 's/[^0-9]//g'`]])
AC_SUBST([CENTOS], [[`rpm --eval '%{centos}'|sed 's/[^0-9]//g'`]])
AC_SUBST([PLATFORM])
AC_SUBST([REVISION], "git"[m4_esyscmd_s([git describe --always])])

if test "$FEDORA"; then
    PLATFORM=Fedora$FEDORA
fi
if test "$RHEL"; then
    DISTRO=RHEL$RHEL
fi
if test "$CENTOS"; then
    DISTRO=CentOS$CENTOS
fi

AM_CONDITIONAL(TARGET_FEDORA, test x"$FEDORA" != x)
AM_CONDITIONAL(TARGET_RHEL, test x"$RHEL" != x && test x"$CENTOS" == x)
AM_CONDITIONAL(TARGET_CENTOS, test x"$CENTOS" != x)
AM_CONDITIONAL(TARGET_EL6, test x"$RHEL" != x || test x"$CENTOS" != x)
AM_CONDITIONAL(TARGET_SYSTEMD, test 0$RHEL -ge 7 || test 0$FEDORA -ge 16 || test 0$CENTOS -ge 7)

AM_PATH_PYTHON

AC_CONFIG_FILES([Makefile
                 src/imgbased/config.py])

AC_OUTPUT

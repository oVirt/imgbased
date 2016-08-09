define([VERSION_MAJOR], [0])
define([VERSION_MINOR], [8])
define([VERSION_FIX], [999])
define([VERSION_NUMBER], VERSION_MAJOR[.]VERSION_MINOR[.]VERSION_FIX)

AC_INIT([imgbased], VERSION_NUMBER, [fabiand@fedoraproject.org])

PACKAGE_RPM_VERSION="VERSION_NUMBER"
AC_SUBST([PACKAGE_RPM_VERSION])

AC_PREFIX_DEFAULT([/usr])
AC_PROG_AWK

AM_INIT_AUTOMAKE([foreign 1.11 -Wall -Wno-portability silent-rules tar-pax no-dist-gzip dist-xz subdir-objects])
AM_MAINTAINER_MODE([enable])
AM_SILENT_RULES([yes])

AC_SUBST([FEDORA],[[`rpm --eval '%{fedora}'|sed 's/[^0-9]//g'`]])
AC_SUBST([RHEL], [[`rpm --eval '%{rhel}'|sed 's/[^0-9]//g'`]])
AC_SUBST([CENTOS], [[`rpm --eval '%{centos}'|sed 's/[^0-9]//g'`]])
AC_SUBST([PLATFORM])
AC_SUBST([REVISION], "git"[m4_esyscmd_s([git log -n1 --format=%h])])
AC_SUBST([RELEASE], [0.[`date '+%Y%m%d%H%M'`]])

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

AC_ARG_VAR([ASCIIDOC], [Path to asciidoc command])
AC_PATH_PROG([ASCIIDOC], [asciidoc])
AM_CONDITIONAL([HAVE_DOCTOOLS], [test "x$ASCIIDOC" != "x"])
if test "x$ASCIIDOC" = "x"; then
        AC_MSG_ERROR([asciidoc not found - cannot create man pages without it])
fi

AM_PATH_PYTHON

AC_CONFIG_FILES([Makefile
                 packaging/rpm/imgbased.spec
                 src/imgbased/config.py])

AC_OUTPUT

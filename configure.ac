dnl
dnl
dnl Copyright (C) 2014-2017  Red Hat, Inc.
dnl
dnl This program is free software; you can redistribute it and/or modify
dnl it under the terms of the GNU General Public License as published by
dnl the Free Software Foundation; either version 2 of the License, or
dnl (at your option) any later version.
dnl
dnl This program is distributed in the hope that it will be useful,
dnl but WITHOUT ANY WARRANTY; without even the implied warranty of
dnl MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
dnl GNU General Public License for more details.
dnl
dnl You should have received a copy of the GNU General Public License
dnl along with this program.  If not, see <http://www.gnu.org/licenses/>.
dnl
define([VERSION_MAJOR], [1])
define([VERSION_MINOR], [2])
define([VERSION_FIX], [14])
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
AC_SUBST([am__tar], ['find "$$tardir" -print -perm /g=w -exec chmod g-w {} \; | sort | tar --no-recursion --mtime="1970-01-01 00:00Z" --owner=root --group=root -chpf - -T -'])

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

AC_CHECK_PROGS(CODESTYLE_CHECKER, [pycodestyle-3 pep8])
AM_CONDITIONAL([HAVE_CODESTYLE_CHECKER], [test "x$CODESTYLE_CHECKER" != "x"])

AC_ARG_VAR([NOSETESTS], [path to nosetests utility])
AC_CHECK_PROGS(NOSETESTS, [nosetests-3 nosetests])
AM_CONDITIONAL([HAVE_NOSETESTS], [test "x$NOSETESTS" != "x"])

AM_PATH_PYTHON

AC_CONFIG_FILES([Makefile
                 packaging/rpm/imgbased.spec
                 src/imgbased/constants.py])

AC_OUTPUT

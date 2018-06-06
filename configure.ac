dnl
dnl
dnl Copyright (C) 2014-2018  Red Hat, Inc.
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
define([VERSION_MINOR], [0])
define([VERSION_FIX], [18])
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

AC_ARG_WITH([python3], AS_HELP_STRING([--with-python3], [Use python3]))

[if test "x$with_python3" == xyes]
[then]
    AC_PATH_PROG([PYTHON3], [python3])
    AC_PATH_PROG([PYFLAKES], [pyflakes-3])

    AC_SUBST([PYTHON3_PREFIX], ['${prefix}'])
    AC_SUBST([PYTHON3_EXEC_PREFIX], ['${exec_prefix}'])

    PYTHON3_DIR=`$PYTHON3 -c "import distutils.sysconfig; \
        print(distutils.sysconfig.get_python_lib(0,0,prefix='$PYTHON3_PREFIX'))"`
    PYTHON3_EXECDIR=`$PYTHON3 -c "import distutils.sysconfig; \
        print(distutils.sysconfig.get_python_lib(1,0,prefix='$PYTHON3_EXEC_PREFIX'))"`

    AC_SUBST(PYTHON3_CFLAGS)
    AC_SUBST(PYTHON3_LIBS)
    AC_SUBST(python3dir, $PYTHON3_DIR)
    AC_SUBST(py3execdir, $PYTHON3_EXECDIR)
    AC_SUBST([pyimagebaseddir], ["\$(python3dir)/imgbased"])
    AC_SUBST([USE_PYTHON_VERSION], [3])
[else]
    AM_PATH_PYTHON([2])
    AC_PATH_PROG([PYFLAKES], [pyflakes-2])
    AC_SUBST([pyimagebaseddir], ["\$(pythondir)/imgbased"])
    AC_SUBST([USE_PYTHON_VERSION], [2])
[fi]

AC_CONFIG_FILES([Makefile
                 packaging/rpm/imgbased.spec
                 src/imgbased/config.py])

AC_OUTPUT

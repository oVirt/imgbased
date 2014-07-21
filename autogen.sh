#!/bin/sh
# Run this to generate configure and Makefile

srcdir=`dirname $0`
test -z "$srcdir" && srcdir=.

THEDIR=`pwd`
(
  cd $srcdir
  die=0

  (autoconf --version) < /dev/null > /dev/null 2>&1 || {
	  echo
	  echo "You must have autoconf installed."
	  echo "Download the appropriate package for your distribution,"
	  echo "or see http://www.gnu.org/software/autoconf"
	  die=1
  }

  # Require libtool only if one of of LT_INIT,
  # AC_PROG_LIBTOOL, AM_PROG_LIBTOOL is used in configure.ac.
  grep -E '^[[:blank:]]*(LT_INIT|A[CM]_PROG_LIBTOOL)' configure.ac >/dev/null \
      && {
    (libtool --version) < /dev/null > /dev/null 2>&1 || {
	  echo
	  echo "You must have libtool installed."
	  echo "Download the appropriate package for your distribution,"
	  echo "or see http://www.gnu.org/software/libtool"
	  die=1
    }
  }

  (automake --version) < /dev/null > /dev/null 2>&1 || {
	  echo
	  die=1
	  echo "You must have automake installed."
	  echo "Download the appropriate package for your distribution,"
	  echo "or see http://www.gnu.org/software/automake"
  }

  test $die = 1 && exit 1

  test -f configure.ac || {
	  echo "You must run this script in the top-level directory"
	  exit 1
  }

  aclocal

  # Run autoheader only if needed
  grep '^[[:blank:]]*AC_CONFIG_HEADERS' configure.ac >/dev/null && autoheader

  automake --add-missing
  autoconf
)

if test "x$OBJ_DIR" != x; then
    mkdir -p "$OBJ_DIR"
    cd "$OBJ_DIR"
fi

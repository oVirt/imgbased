#!/usr/bin/bash

tap_reply() {
  MSG=$1
  shift 1
  eval $@
  rc=$?
  echo ""
  if [[ $rc == 0 ]];
  then
      echo "ok $MSG";
  else
      echo "not ok $MSG";
  fi
}


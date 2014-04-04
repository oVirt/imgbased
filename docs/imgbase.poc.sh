#!/bin/bash

DEBUG=${DEBUG:-true}

VG=HostVG
BASELV=BaseImage
THINPOOL=ImagePool

LAYERPREFIX=Layer
LAYERSIZE=500M

run() {
  [[ ! -z $DEBUG ]] && echo -e $@
  [[ -z $DEBUG ]] && eval $@
}

uuid() {
  tr -d - < /proc/sys/kernel/random/uuid
}

trigger_hook() {
  local NAME=$1
  shift 1
  local ARGS=$@
  local HOOKDIR="/usr/lib/node/hooks/${NAME}.d/"
  run echo "Running hooks for $NAME $ARGS in $HOOKDIR"
  [[ -e $HOOKDIR ]] && for HOOK in ${HOOKDIR}*;
  do
    run echo "Running '$HOOK $ARGS'"
    $HOOK $ARGS
  done
}

add_layer_ontop() {
  local PREVIOUS_LAYER=$1
  local NEW_LAYER=$2
  run lvcreate --snapshot --name $NEW_LAYER ${PREVIOUS_LAYER}
  run lvchange --activate y --setactivationskip n ${PREVIOUS_LAYER}
  run lvchange --activate y --setactivationskip n ${NEW_LAYER}
}

add_boot_entry() {
  local NAME=$1
  local ROOTVG=$2
  local EID=$(uuid)
  local EDIR="/boot/loader/entries"
  local EFILE="${EDIR}/${EID}.conf"
  run mkdir -p ${EDIR}

  grep_boot() { cd /boot ; ls $1 | sort | tail -n1; }
  local LINUX=/$(grep_boot vmlinuz-*.x86_64)
  local INITRAMFS=/$(grep_boot initramfs-*.x86_64.img)

  write_or_show() { [[ -z $DEBUG ]] && tee $@ ; [[ ! -z $DEBUG ]] && cat ; }
  {
  echo "title      $NAME"
  echo "linux      $LINUX"
  echo "initrd     $INITRAMFS"
  echo "options    rd.lvm.lv=$NAME root=$ROOTVG console=ttyS0"
  } | write_or_show $EFILE

  # Now change the fstab of the snapshot
  # so the correct rootfs is mounted
  TMPDIR=$(mktemp -d)
  run mkdir -p $TMPDIR
  run mount ${ROOTVG} ${TMPDIR}
  # Make this a hook
  [[ -z $DEBUG ]] && sed -i "/[ \t]\/[ \t]/ s#^[^ \t]\+#$ROOTVG#" ${TMPDIR}/etc/fstab
  trigger_hook "new-layer-added" / ${TMPDIR}
  run umount ${ROOTVG}
  run rmdir ${TMPDIR}
}

add_bootable_layer() {
  local IDX=$(lvs | egrep "\s+${LAYERPREFIX}" | wc -l)
  local PREVIOUS_LAYER=${LAYERPREFIX}$(( $IDX - 1 ))
  if [[ ${IDX} -eq 0 ]];
  then
    PREVIOUS_LAYER=BaseImage
  fi
  local NEW_LAYER=${LAYERPREFIX}${IDX}
  add_layer_ontop $VG/${PREVIOUS_LAYER} $VG/${NEW_LAYER}
  add_boot_entry $VG/${NEW_LAYER} /dev/mapper/$VG-$NEW_LAYER
}

[[ $1 -eq "add_layer" ]] && add_bootable_layer
[[ -n $DEBUG ]] && echo "DEBUG MODE"


# Later idea            20140101-1.2
#                       +
#                  20140101-1.1
#                  +
#  20140101-1.0  -------->  20140303

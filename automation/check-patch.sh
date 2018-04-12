#!/bin/bash -xe

ARTIFACTSDIR=$HOME/exported-artifacts
TMPDIR=$HOME/tmp
NGNDIR=$TMPDIR/ngn/ovirt-node-ng

IMG_INI=4
IMG_UPD=5

save_logs() {
    cp -fv *.{log,conf} $ARTIFACTSDIR || :
}

setup_environ() {
    seq 0 9 | xargs -I {} mknod /dev/loop{} b 7 {} || :
    mknod /dev/kvm c 10 232 || :

    mkdir $ARTIFACTSDIR || :
    rm -rf $TMPDIR && mkdir $TMPDIR
    mkdir -p $NGNDIR

    export TMPDIR
}

build_imgbased() {
    ./autogen.sh
    ./configure
    make -j5 check
}

fetch_node_iso() {
    local job_url=$(sed -e 's/imgbased/ovirt-node-ng/' \
                        -e 's/check-patch/build-artifacts/' <<< $JOB_URL)

    local build_num=$(wget -qO- $job_url/lastSuccessfulBuild/buildNumber)
    local artifacts_url="$job_url/$build_num/api/json?tree=artifacts[fileName]"

    local iso=$(wget -qO- $artifacts_url | grep -Po '[^[:space:]"]*\.iso')

    [[ -z $iso ]] && {
        echo "ISO not found, install/upgrade will not be checked"
        exit 0
    }

    echo "Downloading iso"

    wget -q "${job_url}/${build_num}/artifact/exported-artifacts/${iso}"
}

build_test_images() {
    echo "Injecting imgbased rpms to squashfs"

    # Extract the squashfs from the iso
    local mntdir=$(mktemp -d)
    mount ovirt*installer*.iso $mntdir
    unsquashfs $mntdir/ovirt-node-ng-image.squashfs.img
    umount $mntdir

    # Install imgbased rpms inside the image
    mount squashfs-root/LiveOS/rootfs.img $mntdir
    local rpms=$(find rpmbuild -name "*imgbased*.noarch.rpm")
    rpm -Uhv --noscripts --force --root=$mntdir $rpms

    # Build 2 new squashfs images (ver-4 and ver-5)
    for x in {$IMG_INI,$IMG_UPD}
    do
        nvr="ovirt-node-ng-${x}.0.0-0.$(date +%Y%m%d).0"
        echo -n "$nvr" > $mntdir/usr/share/imgbase/build/meta/nvr
        sync $mntdir && umount $mntdir
        mksquashfs squashfs-root image.squashfs.${x} -noI -noD -noF -noX
        [[ $x -eq $IMG_INI ]] && mount squashfs-root/LiveOS/rootfs.img $mntdir
    done

    rm -rf squasfs-root
    rmdir $mntdir
}

repack_node_artifacts() {
    local mntdir=$(mktemp -d)
    local extdir=$(mktemp -d)
    local iso="ovirt-node-ng-installer*.iso"
    local volid=$(isoinfo -d -i $iso | grep -Po "(?<=Volume id: ).*")

    # Extract the iso to extdir
    mount $iso $mntdir
    pushd $mntdir
    tar cf - . | (cd $extdir && tar xf -)
    popd
    umount $mntdir
    rmdir $mntdir

    # Copy the init image to the extracted iso dir
    mv image.squashfs.$IMG_INI $extdir/ovirt-node-ng-image.squashfs.img

    # Repack the iso with the new image
    pushd $extdir
    mkisofs -o $ARTIFACTSDIR/ovirt-test-installer.iso \
            -b isolinux/isolinux.bin \
            -c isolinux/boot.cat \
            -no-emul-boot \
            -boot-load-size 4 \
            -boot-info-table -J -R -V "$volid" .
    popd
    implantisomd5 $ARTIFACTSDIR/ovirt-test-installer.iso
    rm -rf $extdir

    # Build image-update rpm with the new update squashfs (ver.5)
    git clone https://gerrit.ovirt.org/ovirt-node-ng $NGNDIR
    mv image.squashfs.$IMG_UPD $NGNDIR/ovirt-node-ng-image.squashfs.img
    pushd $NGNDIR
    git checkout $GERRIT_BRANCH
    ./autogen.sh
    touch boot.iso
    touch ovirt-node-ng-image.{squashfs.img,manifest-rpm,unsigned-rpms}
    make rpm PLACEHOLDER_RPM_VERSION=$IMG_UPD PLACEHOLDER_RPM_RELEASE=0
    find tmp.repos -name "ovirt*image-update*.rpm" -exec mv {} $ARTIFACTSDIR \;
    git checkout -
    popd
}

do_ssh() {
    local ssh_key=$1
    local ip=$2
    local cmd=$3
    local lim=${4:-1}

    for i in $(seq 1 $lim)
    do
        ssh -q -o "UserKnownHostsFile /dev/null" \
               -o "StrictHostKeyChecking no" \
               -i $ssh_key root@$ip $cmd && break ||:
        sleep 5
    done
}

run_nodectl_check() {
    local name=$1
    local ssh_key=$2
    local ip=$3
    local outfile=$4

    local timeout=120
    local check=""

    while [[ -z "$check" ]]
    do
        [[ $timeout -eq 0 ]] && break
        check=$(do_ssh $ssh_key $ip "nodectl check" 10 2>&1)
        sleep 10
        timeout=$((timeout - 10))
    done

    echo "$check" > $outfile
}

validate_nodectl_log() {
    local logfile=$1

    cat $logfile

    status=$(grep -Po "(?<=Status: ).*" $logfile)
    [[ "$status" == *OK* ]] || {
        echo "Invalid node status"
        exit 1
    }
}

iso_install_upgrade() {
    # Install the iso
    $NGNDIR/scripts/node-setup/setup-node-appliance.sh \
        -i $ARTIFACTSDIR/ovirt-test-installer.iso \
        -p ovirt > setup-iso.log 2>&1

    mv *nodectl-check*.log init-nodectl-check.log
    validate_nodectl_log "init-nodectl-check.log"

    # Grab name, sshkey and addr, ugly but works
    local name=$(grep available setup-iso.log | cut -d: -f1)
    local addr=$(grep -Po "(?<=at ).*" setup-iso.log)
    local sshkey="/var/lib/virtual-machines/sshkey-${name}"

    # Check the current iso layer name
    do_ssh $sshkey $addr "imgbase layout; imgbase w" > init-layers.log 2>&1

    # Copy update rpm to node
    scp -o "UserKnownHostsFile /dev/null" \
        -o "StrictHostKeyChecking no" \
        -i $sshkey $ARTIFACTSDIR/*.rpm root@$addr:

    # Install the update rpm
    do_ssh $sshkey $addr "rpm -Uhv \"*.rpm\""

    # Copy the imgbased.log file
    local logfile=$(rpm -qp --scripts $ARTIFACTSDIR/*.rpm | \
                    grep imgbased.log | \
                    awk '{print $8}')

    scp -o "UserKnownHostsFile /dev/null" \
        -o "StrictHostKeyChecking no" \
        -i $sshkey root@$addr:$logfile .

    # Reboot
    do_ssh $sshkey $addr "reboot" > /dev/null
    run_nodectl_check "$name" "$sshkey" "$addr" "upgrade-nodectl-check.log"
    validate_nodectl_log "upgrade-nodectl-check.log"

    # Check the current iso layer name and layout
    do_ssh $sshkey $addr "imgbase layout; imgbase w" > upgrade-layers.log 2>&1
}

main() {
    trap save_logs EXIT

    setup_environ
    build_imgbased
    fetch_node_iso
    build_test_images
    repack_node_artifacts
    iso_install_upgrade
}

main

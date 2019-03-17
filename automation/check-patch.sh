#!/bin/bash -ex

ARTIFACTSDIR=$HOME/exported-artifacts
TMPDIR=$HOME/tmp
NGNDIR=$TMPDIR/ngn/ovirt-node-ng-image
COVDIR=/var/lib/imgbase-coverage

IMG_INI=4
IMG_UPD=5
IMG_TST=6

save_logs() {
    cp -fv *.log $ARTIFACTSDIR || :
}

setup_environ() {
    seq 0 9 | xargs -I {} mknod /dev/loop{} b 7 {} || :
    mknod /dev/kvm c 10 232 || :
    mknod /dev/vhost-net c 10 238 || :
    mkdir /dev/net || :
    mknod /dev/net/tun c 10 200 || :

    mkdir $ARTIFACTSDIR || :
    rm -rf $TMPDIR && mkdir $TMPDIR
    mkdir -p $NGNDIR

    export TMPDIR
    export DIST="$(rpm --eval %{dist} | cut -d. -f2)"
}

build_imgbased() {
    ./autogen.sh
    ./configure
    make -j5 check
    find rpmbuild -name "*.rpm" -exec cp -vf {} $ARTIFACTSDIR \;
}

fetch_node_iso() {
    local ver="${GERRIT_BRANCH#*-}"
    local arch="$(rpm --eval %{_arch})"
    local job_url="http://jenkins.ovirt.org/job/ovirt-node-ng-image_${ver}_build-artifacts-${DIST}-${arch}/"

    local build_num=$(wget -qO- $job_url/lastSuccessfulBuild/buildNumber)
    local artifacts_url="$job_url/$build_num/api/json?tree=artifacts[fileName]"

    local iso=$(wget -qO- $artifacts_url | grep -Po '[^[:space:]"]*\.iso')

    [[ -z $iso ]] && {
        echo "ISO not found, install/upgrade will not be checked"
        exit 0
    }

    local iso_url="${job_url}/${build_num}/artifact/exported-artifacts/${iso}"
    echo "Downloading: $iso_url"
    wget -q $iso_url
}

build_test_images() {
    echo "Injecting imgbased rpms to squashfs"

    # Extract the squashfs from the iso
    local mntdir=$(mktemp -d)
    mount ovirt*installer*.iso $mntdir
    unsquashfs $mntdir/ovirt-node-ng-image.squashfs.img
    umount $mntdir

    # Install imgbased and coverage rpms inside the image
    mount squashfs-root/LiveOS/rootfs.img $mntdir
    local rpms=$(find rpmbuild -name "*imgbased*.noarch.rpm")

    # Free some space for testing
    rm -rf $mntdir/usr/share/factory/var/cache/*
    rm -rf $mntdir/usr/share/{locale,doc}


    if [[ ${DIST} = fc* ]]; then
        export PACKAGER=dnf
        export COVERAGE=coverage3
        dnf config-manager -q --installroot=$mntdir --set-enabled fedora updates
        ${PACKAGER} install --installroot=$mntdir -y python3-coverage $rpms
        ${PACKAGER} clean all --installroot=$mntdir
        dnf config-manager -q --installroot=$mntdir --set-disabled fedora updates
    else
        export PACKAGER=yum
        export COVERAGE=coverage
        yum-config-manager -q --installroot=$mntdir --enable base,updates
        ${PACKAGER} install --installroot=$mntdir -y python-coverage $rpms
        ${PACKAGER} clean all --installroot=$mntdir
        yum-config-manager -q --installroot=$mntdir --disable base,updates
    fi

    mkdir -p $mntdir/$COVDIR
    sed -e '/^$PYTHON/d' -e 's/bash/bash -x/' -i $mntdir/usr/sbin/imgbase
    cat << EOF >> $mntdir/usr/sbin/imgbase
export COVERAGE_FILE=\$(mktemp -u $COVDIR/.coverage.imgbase_XXXXXXXXXXXXXX)
${COVERAGE} run -m imgbased.__main__ \$@
EOF

    # Build 2 new squashfs images (ver-4 and ver-5)
    for x in {$IMG_INI,$IMG_UPD}
    do
        nvr="ovirt-node-ng-${x}.0.0-0.$(date +%Y%m%d).0"

        # Reverse the image state and check image-build
        chroot $mntdir << EOF
mknod /dev/urandom c 1 9
rm -rf /usr/share/factory/{etc,var}
rm -f /var/lib/{rpm,${PACKAGER}}
mv /usr/share/{rpm,${PACKAGER}} /var/lib
touch /etc/{resolv.conf,hostname,iscsi/initiatorname.iscsi}
imgbase --debug --experimental image-build --postprocess --set-nvr=$nvr
rm /dev/urandom
EOF
        sync $mntdir && umount $mntdir
        mksquashfs squashfs-root image.squashfs.${x}
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
    mkisofs -o $TMPDIR/ovirt-test-installer.iso \
            -b isolinux/isolinux.bin \
            -c isolinux/boot.cat \
            -no-emul-boot \
            -quiet \
            -boot-load-size 4 \
            -boot-info-table -J -R -V "$volid" .
    popd
    implantisomd5 $TMPDIR/ovirt-test-installer.iso
    rm -rf $extdir

    # Build image-update rpm with the new update squashfs (ver.5)
    git clone https://gerrit.ovirt.org/ovirt-node-ng-image $NGNDIR
    mv image.squashfs.$IMG_UPD $NGNDIR/ovirt-node-ng-image.squashfs.img
    pushd $NGNDIR
    git checkout $GERRIT_BRANCH
    ./autogen.sh
    sed -i ovirt-node-ng.spec.in \
        -e 's/set -e/set -ex/' \
        -e 's/--quiet//' \
        -e 's/null/stdout/' \
        -e 's#^export PYTHONPATH.*#export PYTHONPATH=$(find $MNTDIR/usr/lib/python* -name imgbased -type d -exec dirname {} \\; | sort | tail -1):$PYTHONPATH#'
    touch boot.iso
    touch ovirt-node-ng-image.{squashfs.img,manifest-rpm,unsigned-rpms}
    make rpm PLACEHOLDER_RPM_VERSION=$IMG_UPD PLACEHOLDER_RPM_RELEASE=0
    find tmp.repos -name "ovirt*image-update*.rpm" -exec mv {} $TMPDIR \;
    cp -fv $TMPDIR/*.noarch.rpm $ARTIFACTSDIR
    git checkout -
    popd
}

exec_ssh() {
    local sshkey=$1
    local addr=$2
    local cmd=$3

    ssh -q -o "UserKnownHostsFile /dev/null" \
           -o "StrictHostKeyChecking no" \
           -i $sshkey root@$addr "$cmd"
}

run_nodectl_check() {
    local bootnum=$1
    local sshkey=$2
    local addr=$3
    local outfile=$4
    local check=""

    for i in {1..30}
    do
        bootcur=$(exec_ssh $sshkey $addr "journalctl --list-boots | wc -l")||:
        echo "Received bootcur=$bootcur, bootnum=$bootnum"
        [[ -z "$bootnum" || "$bootcur" = "$bootnum" ]] && {
            exec_ssh $sshkey $addr "nodectl check" > $outfile 2>&1 ||:
            grep "Status:" $outfile && break
        }
        sleep 10
    done
}

fetch_remote() {
    local sshkey=$1
    local addr=$2
    local path=$3
    local dest=$4
    local compress=$5

    scp -o "UserKnownHostsFile /dev/null" \
        -o "StrictHostKeyChecking no" \
        -i $sshkey -r root@$addr:$path $dest ||:

    [[ -n $compress ]] && {
        tar czf $dest.tgz $dest && mv $dest.tgz $ARTIFACTSDIR
    }||:
}

validate_nodectl_log() {
    local logfile=$1
    local sshkey=$2
    local addr=$3

    cat $logfile

    status=$(grep -Po "(?<=Status: ).*" $logfile)
    [[ "$status" == *OK* ]] || {
        echo "Invalid node status"
        exit 1
    }
}

iso_install_upgrade() {
    echo "Installing $TMPDIR/ovirt-test-installer.iso"
    # Install the iso
    ISO_INSTALL_TIMEOUT=45 $NGNDIR/scripts/node-setup/setup-node-appliance.sh \
        -i $TMPDIR/ovirt-test-installer.iso \
        -p ovirt > setup-iso.log 2>&1 || setup_rc=$?

    rm -f *nodectl-check.log

    # Grab name, sshkey and addr, ugly but works
    local name=$(grep available setup-iso.log | cut -d: -f1)
    local addr=$(grep -Po "(?<=at ).*" setup-iso.log)
    local wrkdir=$(grep -Po "(?<=WORKDIR: ).*" setup-iso.log)
    local sshkey="$wrkdir/sshkey-${name}"

    fetch_remote "$sshkey" "$addr" "/tmp" "init_tmp" "1"
    fetch_remote "$sshkey" "$addr" "/var/log" "init_var_log" "1"
    fetch_remote "$sshkey" "$addr" "/etc" "init_etc" "1"

    [[ $setup_rc -ne 0 ]] && {
        mv $TMPDIR/ovirt-test-installer.iso $ARTIFACTSDIR
        echo "ISO install failed, exiting"
        exit 1
    }

    echo "Validating nodectl check"
    run_nodectl_check "" "$sshkey" "$addr" "init-nodectl-check.log"
    validate_nodectl_log "init-nodectl-check.log" "$sshkey" "$addr"

    # Check the current iso layer name
    exec_ssh $sshkey $addr "imgbase layout; imgbase w" > init-layers.log 2>&1

    # Make sure we have persistent storage for journalctl
    exec_ssh $sshkey $addr "echo 3 > /proc/sys/vm/drop_caches; mkdir -p /var/log/journal"

    # Count boot number
    local bootnum=$(exec_ssh $sshkey $addr "journalctl --list-boots | wc -l")

    # Build, send and install imgbased-persist rpm
    rpmbuild -bb packaging/rpm/imgbased-persist.spec
    find rpmbuild -name imgbased-persist*.rpm -exec mv {} $TMPDIR \;

    # Copy update and persist rpms to node
    scp -o "UserKnownHostsFile /dev/null" \
        -o "StrictHostKeyChecking no" \
        -i $sshkey $TMPDIR/*.rpm root@$addr:

    # Install the update rpm
    echo "Installing update rpm"
    exec_ssh $sshkey $addr << EOF 2>&1 || failed=1
${PACKAGER} install -y imgbased-persist*.rpm
rm imgbased-persist*.rpm
rpm -Uhv \"*.rpm\"
EOF

    # Grab some logs
    echo "Downloading remote logs"
    local logfile=$(rpm -qp --scripts $TMPDIR/ovirt*image-update*.rpm | \
                    grep imgbased.log | \
                    awk '{print $8}')

    fetch_remote "$sshkey" "$addr" "$logfile" "imgbased.log"
    fetch_remote "$sshkey" "$addr" "/var/log" "post_upgrade_var_log" "1"
    fetch_remote "$sshkey" "$addr" "/etc" "post_upgrade_etc" "1"

    [[ $failed -eq 1 ]] && {
        echo "Upgrade rpm failed, check post-upgrade logs for details"
        exit 1
    }

    # Reboot
    echo "Rebooting, bootnum=$bootnum"
    exec_ssh $sshkey $addr "reboot" ||:

    # Run checks when sshd is up
    echo "Running some more tests and gathering coverage data"
    run_nodectl_check "$((bootnum+1))" "$sshkey" "$addr" "upgrade-nodectl-check.log"
    fetch_remote "$sshkey" "$addr" "/var/log" "post_reboot_var_log" "1"
    fetch_remote "$sshkey" "$addr" "/etc" "post_reboot_etc" "1"
    validate_nodectl_log "upgrade-nodectl-check.log" "$sshkey" "$addr"

    local test_nvr="ovirt-node-ng-${IMG_TST}.0.0-0.$(date +%Y%m%d).0"
    local prev_nvr="ovirt-node-ng-${IMG_INI}.0.0-0.$(date +%Y%m%d).0"
    local scap_ds="/usr/share/xml/scap/ssg/content/ssg-centos7-ds.xml"
    local scap_profile="xccdf_org.ssgproject.content_profile_stig-rhel7-disa"
    # Run some imgbase checks to collect more coverage, this will destroy the
    # vm (make it not bootable), it's OK
    exec_ssh $sshkey $addr << EOF > post-checks.log 2>&1
imgbase check
imgbase layout
imgbase w
rm /etc/iscsi/initiatorname.iscsi
touch /var/lib/ngn-vdsm-need-configure
imgbase --debug service --start
imgbase --debug service --stop
imgbase --debug openscap --register $scap_ds $scap_profile
imgbase --debug openscap --list
imgbase --debug openscap --all
imgbase --debug openscap --scan /
imgbase --debug openscap --unregister $scap_profile
imgbase --debug layout --free-space
imgbase --debug layout --bases
imgbase --debug --experimental volume --list
imgbase --debug --experimental diff \$(imgbase layout --layers)
imgbase --debug --experimental factory-diff --config=NA
imgbase --debug --experimental pkg --diff \$(imgbase layout --layers)
imgbase --debug --experimental nspawn $prev_nvr+1 ls /
vg=\$(vgs --noheadings|awk '{print \$1}')
lvcreate --snapshot --name \$vg/$test_nvr $prev_nvr
lvcreate --snapshot --name \$vg/$test_nvr+1 $test_nvr
lvchange --addtag imgbased:layer \$vg/$test_nvr \$vg/$test_nvr+1
imgbase --debug layout
imgbase --debug --experimental recover --list
imgbase --debug --experimental recover --force
imgbase --debug rollback --to $prev_nvr
imgbase --debug base --latest
imgbase --debug base --remove $prev_nvr
imgbase --debug --experimental volume --create /var/crash 1G
rpm -q imgbased-persist
EOF

    fetch_remote "$sshkey" "$addr" "$COVDIR" $ARTIFACTSDIR/coverage-data
    cp -vr $ARTIFACTSDIR/coverage-data/. .
    cat << EOF >> .coveragerc
[run]
omit =
    /*/site-packages/six*
    /usr/lib/python3.6/site-packages/pkg_resources*
    /usr/lib/python3.6/site-packages/six*

[paths]
source =
    src/imgbased
    /usr/lib/python2.7/site-packages/imgbased
    /tmp/*/usr/lib/python2.7/site-packages/imgbased
    /usr/lib/python3.6/site-packages/imgbased
    /tmp/*/usr/lib/python3.6/site-packages/imgbased
EOF

    ${COVERAGE} combine
    ${COVERAGE} html -i -d $ARTIFACTSDIR/coverage-report
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

# imgbased

[![Copr build status](https://copr.fedorainfracloud.org/coprs/ovirt/ovirt-master-snapshot/package/imgbased/status_image/last_build.png)](https://copr.fedorainfracloud.org/coprs/ovirt/ovirt-master-snapshot/package/imgbased/)

Welcome to the oVirt imgbased source repository. This repository is hosted on [GitHub:imgbased](https://github.com/oVirt/imgbased).

imgbased provides a specific management method to derive writeable filesystem
layers from read-only base images.
It also takes care that the layer which shall be used can be selected at boot
time.

In a nutshell this works by:
 * having a boot partition
 * and having a default LVM volume group (*HostVG*)
 * which has a *thinpool*
 * each *base* is kept in a read-only thin logical volume in the *thinpool*
 * for each *base* at least one writable *layer*, which is a thin logical
   volume, is created in the *thinpool*
 * for each *layer* a boot entry is created which can be used to boot in a
   specific layer

For more details see below.


## How to contribute

All contributions are welcome - patches, bug reports, and documentation issues.

### Submitting patches

Please submit patches to [GitHub:imgbased](https://github.com/oVirt/imgbased). If you are not familiar with the process, you can read about [collaborating with pull requests](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests) on the GitHub website.

### Found a bug or documentation issue?

To submit a bug or suggest an enhancement for oVirt imgbased please use [oVirt Bugzilla](https://bugzilla.redhat.com/enter_bug.cgi?product=imgbased).

If you don't have a Bugzilla account, you can still report [issues](https://github.com/oVirt/imgbased/issues). If you find a documentation issue on the oVirt website, please navigate to the page footer and click "Report an issue on GitHub".

## Still need help?

If you have any other questions or suggestions, you can join and contact us on the [oVirt Users forum / mailing list](https://lists.ovirt.org/admin/lists/users.ovirt.org/).



## Build the tool

How to build the tools.

    sudo yum install -y make autoconf automake python
    git clean -fdx
    ./autogen.sh
    make dist
    rpmbuild -ta imgbased-*.tar.xz



## Using `imgbase`

To use the `imgbase` tool you need a Fedora or CentOS image, which was
installed using the `autopart --type=thinp` directive.
`imgbased` can be used to create new *layers* and install new *bases*.

    # To create the assumed LVM layout
    imgbase layout --init Base-1-0 --from /

    # List existing layers and bases
    imgbase layout

    # Add a new base
    # The `--size` argument specifies the size of the underlying
    # logical volume. It must be at least the size of the filesystem
    # contained in `$IMGFILE`.
    imgbase base --add Base-2-0 --size 1G

    # Get the latest base (which will be used for subsequent layers)
    imgbase base --latest

    # Add a new layer on the latest base or latest layer of the latest base
    imgbase layer --add Base-1-0

    # And with more infos
    imgbase --debug layer --add


## Purpose

Provide a more flexible solution for [oVirt Node](http://www.ovirt.org/Node).
Mainly a way where we can re-use existing technologies like anaconda.


## High-Level Things

 * Read-Only bases (see also Drawbacks)
 * Write-able layers
 * Boot into layers
 * No inheritance between bases
 * *Persistence* between bases
    * Copy files between Base-N to Base-(N+1)


## Features

 * Based on stable things (LVM, ext4)
 * A real filesystem (the *layer*) is modified and is used for boot
    * This solves all sort of problems with early boot
 * Sparseness everywhere
    * LVM with thinpool and thinvolume (frees space on discard operation)
    * ext4 FS with discard option (frees space after file removal)
 * LiveCD is only the delivery method
    * rootfs image is used at runtime
 * More distro agnostic than LiveCD
    * dracut, lvm (with thin volumes) and ext4 are the requirements

## Drawbacks

 * Not as read-only as LiveCD-everywhere approach
    * The rootfs is kept on a ro LV, if this is changed to rw then the original
      base lv can be changed.
      This wasn't possible when the LiveCD was stored, because the rootfs was
      in a (as by limitation) read-only squashfs.
 * The persistence is a copy
    * When a new base image is installed, the persistence of configuration
      (and other) files from the previous base happens by copying the files.
      Previously bind mounts were used to achieve this.
 * Runtime space requirements are higher compared to LiveCD runtime
    * The LiveCD based delivery will be comparable in size.


## LVM Structure

Assumptions about the host:

    + VG
    |
    +--+ Config (LV)
    |
    +--+ Base-1-0 (LV, ro)
    |   \
    |    \
    |     + Base-1-0+1 (LV, rw)
    |     |
    |     + Base-1-0+2 (LV, rw)
    |
    |
    +--+ Base-2-0 (LV, ro)
    |   \
    |    \
    |     + Base-2-0+1 (LV, rw)
    :     :

With a boot entry for each Base-\* this allows the user to boot into each
Base-LV.
Changes are inherited from each Base-\* and can also be persisted using the
Config LV.


## LiveCD Payload

The image is the (in future) intended to be also used as a paylod for LiveCD
ISOs and to be deployed via PXE.
Because of this we want to minimize the image even further. For this
[virt-sparsify](http://libguestfs.org/virt-sparsify.1.html) and squashfs
can be used to simulate the size of the image when it is used as a payload.

    # To get an idea of the minimized size use
    make runtime-layout.squash

The LiveCD will be created the livemedia-creator which is part of
[lorax](https://git.fedorahosted.org/cgit/lorax.git/).

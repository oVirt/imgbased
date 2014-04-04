imgbased
========

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

Build the tool
--------------

How to build the tools.

    git clean -fdx
    ./autogen.sh
    make dist
    rpmbuild -ta imgbased-*.tar.xz

Build an image
--------------

The repository also contains some example kickstarts which create an image with
the correct LVm layout to get started with this tool.

> Note: The image will not contain the *imgbased* package, you will need to
> install this manually

    # Lorax provides livemedia-creator
    sudo yum install -y lorax

    # First create the kickstarts
    make dist

    # A boot iso is required by lorax, use Fedora 20
    curl -O http://${mirror-url}/releases/20/Fedora/x86_64/os/images/boot.iso

    # Kickoff the image creation
    livemedia-creator \
      --make-fsimage \
      --iso boot.iso \
      --ks data/kickstarts/runtime-layout.ks \
      --vcpus 4 \
      --image-name imgbased.img


High-Level Things
-----------------

 * Read-Only bases (see also Drawbacks)
 * Write-able layers
 * Boot into layers
 * No inheritance between bases
 * *Persistence* between bases
    * Copy files between Base-N to Base-(N+1)


Features
--------

 * Based on stable things (LVM, ext4)
 * A real filesystem (the *layer*) is modified and is used for boot
    * This solves all sort of problems with early boot
 * Sparseness everywhere
    * LVM with thinpool and thinvolume (frees space on discard operation)
    * ext4 FS with discard option (frees space after file removal)
 * LiveCD is only the delivery method
    * rootfs image is used at runtime


Drawbacks
---------

 * Not as read-only as LiveCD-everywhere approach
    * The rootfs is kept on a ro LV, if this is changed to rw then the original
      base lv can be changed.
      This wasn't possible when the LiveCD was stored, because the rootfs was
      in a (as by limitation) read-only squashfs.
 * The persistence is a copy
    * When a new base image is installed, the persistence of configuration
      (and other) files from the previous base happens by copying the files.
      Previously bind mounts were used to achieve this.


LVM Structure
-------------

Assumptions about the host:

    + VG
    |
    +--+ Config (LV)
    |
    +--+ Base-0 (LV, ro)
       |\
       | \
       |  + Base-0.1 (LV, rw)
       |  |
       |  + Base-0.2 (LV, rw)
       |
       |
       + Base-1 (LV, ro)
       :

With a boot entry for each Base-\* this allows the user to boot into each
Base-LV.
Changes are inherited from each Base-\* and can also be persisted using the
Config LV.

imgbased
========

imgbased is a set of tools to work with images on a host


Build
-----

    git clean -fdx
    ./autogen.sh
    make dist
    rpmbuild -ta imgbased-*.tar.xz


High-Level Things
-----------------

 * Read-Only bases
 * Write-able snapshots
 * Boot into snapshots
 * No inheritance between Bases
 * *Persistence* between bases
    * Copy files between Base-N to Base-N+1


Structure
---------

Assumptions about the host:

    + VG
      + Config (LV)
      |
      + Base-0 (LV, ro)
      |\
      | + Base-0.1 (LV, rw)
      |  \
      |   + Base-0.2 (LV, rw)
      |
      + Base-1 (LV, ro)
      :

With a boot entry for each Base-\* this allows the user to boot into each Base-LV.
Changes are inherited from each Base-\* and can also be persisted using the Config LV.

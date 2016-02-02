#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# imgbase
#
# Copyright (C) 2015  Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Author(s): Fabian Deutsch <fabiand@redhat.com>
#

import logging
import re
import rpm

log = logging.getLogger(__package__)


class NamingScheme():
    datasource = None

    def __init__(self, datasource):
        self.datasource = datasource

    def image_from_name(self, name):
        raise NotImplementedError

    def tree(self):
        """Returns an ordered list of bases and children
        """
        raise NotImplementedError

    def images(self):
        images = []
        for base in self.bases():
            images.append(base)
            images.extend(base.layers)
        return sorted(images)

    def bases(self):
        bases = sorted(self.tree())
        assert all(b.is_base() for b in bases)
        return bases

    def layers(self, for_base=None):
        layers = []
        for b in self.tree():
            if for_base is None or (for_base and b == for_base):
                layers.extend(b.layers)
        return sorted(layers)

    def last_base(self):
        bases = self.bases()
        assert bases
        return bases.pop()

    def last_layer(self):
        layers = self.layers()
        assert layers
        return layers.pop()

    def layer_before(self, other_layer):
        layers = self.layers()
        assert other_layer in layers
        oidx = layers.index(other_layer)
        return layers[oidx-1]

    def suggest_next_layer(self, prev_img):
        """Determine the LV name of the next layer (based on the scheme)

        image: Layer or Base
        """
        log.debug("Finding next layer based on %r" % prev_img)
        if prev_img.is_base():
            log.debug("Suggesting for layer for base %s" % prev_img)
            if prev_img.layers:
                log.debug("... with layers")
                last_layer = sorted(prev_img.layers).pop()
                next_index = int(last_layer.index) + 1
            else:
                log.debug("... without layers")
                next_index = 1
            next_img = prev_img.derive_layer(next_index)
        elif prev_img.is_layer():
            log.debug("Suggesting for layer for prev layer %s" % prev_img)
            next_index = int(prev_img.index) + 1
            next_img = prev_img.base.derive_layer(next_index)
        else:
            assert False, "Should not be reached"

        # assert next_img not in self.layers()

        return next_img

    def layout(self, lvs=None):
        """List all bases and layers for humans
        """
        idx = []
        try:
            tree = self.tree(lvs)
        except RuntimeError:
            raise RuntimeError("No valid layout found. Initialize if needed.")

        for base in tree:
            idx.append("%s" % base)
            for layer in base.layers:
                c = u"└" if layer is base.layers[-1] else u"├"
                idx.append(u" %s╼ %s" % (c, layer))
        return u"\n".join(idx)


class NvrNaming(NamingScheme):
    """This class is for parsing nvr like schemes.
    Example: Name-Ver.sion-Re.lease

    >>> layers = NvrNaming([])
    >>> layers.last_base()
    Traceback (most recent call last):
    ...
    RuntimeError: No bases found: []

    >>> names = ["Image-1-0", "Image-13-0", "Image-13-0+1",
    ... "Image-2-0+1", "Image-2-0"]
    >>> layers = NvrNaming(names)

    >>> sorted(layers.tree())
    [<Base Image-1-0 [] />, <Base Image-2-0 [<Layer Image-2-0+1 />] />, \
<Base Image-13-0 [<Layer Image-13-0+1 />] />]

    >>> layers.last_base()
    <Base Image-13-0 [<Layer Image-13-0+1 />] />

    >>> layers = NvrNaming([])
    >>> layers.last_layer()
    Traceback (most recent call last):
    ...
    RuntimeError: No bases found: []

    >>> names = ["Image-0-0", "Image-13-0", "Image-13-0+1", "Image-2-0"]
    >>> layers = NvrNaming(names)
    >>> layers.last_layer()
    <Layer Image-13-0+1 />

    >>> layers.layers()
    [<Layer Image-13-0+1 />]

    >>> layers.layers(for_base=Base("Image-13-0"))
    [<Layer Image-13-0+1 />]

    >>> prev_img = Base("Image-0-0")
    >>> names = [str(prev_img)]
    >>> layers = NvrNaming(names)
    >>> layers.suggest_next_layer(prev_img)
    <Layer Image-0-0+1 />

    >>> names = ["Image-0-0", "Image-13-0", "Image-13-0+1",
    ... "Image-2-0", "Image-2-0+1"]
    >>> layers = NvrNaming(names)
    >>> layers.suggest_next_layer(Base("Image-13-0", [Layer("Image-13-0+1")]))
    <Layer Image-13-0+2 />

    >>> layers.suggest_next_layer(Layer("Image-2-0+1"))
    <Layer Image-2-0+2 />


    >>> layers = NvrNaming([])
    >>> layers.layout()
    Traceback (most recent call last):
    ...
    RuntimeError: No valid layout found. Initialize if needed.

    >>> names = ["Image-2-0+1", "Image-2-0", "Image-2-0+2"]
    >>> layers = NvrNaming(names)
    >>> layers.layout()
    u'Image-2-0\\n \u251c\u257c Image-2-0+1\\n \u2514\u257c Image-2-0+2'
    """

    def tree(self, datasource=None):
        """Returns a list of bases and children
        >>> layers = NvrNaming([])
        >>> layers.tree()
        Traceback (most recent call last):
        ...
        RuntimeError: No bases found: []

        >>> names = ["Image-0-0", "Image-13-0", "Image-2-0+1",
        ... "Image-2-0"]
        >>> layers = NvrNaming(names)
        >>> layers.tree()
        [<Base Image-0-0 [] />, <Base Image-2-0 [<Layer Image-2-0+1 />] />, \
<Base Image-13-0 [] />]
        """
        datasource = datasource or self.datasource
        if callable(datasource):
            names = datasource()
        else:
            names = datasource

        log.debug("Names: %s" % names)
        images = []
        for name in names:
            try:
                images.append(self.image_from_name(name))
            except:
                log.debug("Failed to parse name %r" % name)
                continue

        log.debug("Images: %s" % images)
        bases = {}
        for img in sorted(images):
            if img.is_base():
                bases[img.nvr] = img
            else:
                bases[img.base.nvr].layers.append(img)
        log.debug("Bases: %s" % bases.values())

        if len(bases.values()) == 0:
            raise RuntimeError("No bases found: %s" % names)

        return list(sorted(bases.values()))

    def image_from_name(self, name):
        """
        >>> naming = NvrNaming(["Image-1-0", "Image-24-0"])
        >>> naming.image_from_name("Image-1-0")
        <Base Image-1-0 [] />
        >>> naming.image_from_name("Image-24-0")
        <Base Image-24-0 [] />
        >>> naming.image_from_name("Image-24-0+1")
        <Layer Image-24-0+1 />
        """
        return Image.from_nvr(name)


class NVR(object):
    """Simple clas to parse and compare NVRs

    >>> nvr = NVR.parse("package-1.2.3-4.el6")
    >>> nvr.name
    'package'
    >>> nvr.version
    '1.2.3'
    >>> nvr.release
    '4.el6'

    >>> second = NVR.parse("package-1.2.3-5.el6")
    >>> nvr < second
    True

    >>> third = NVR.parse("package-2.2.3-4.el6")
    >>> nvr < third
    True

    >>> lst = [second, third, nvr]
    >>> lst
    [<NVR package-1.2.3-5.el6 />, <NVR package-2.2.3-4.el6 />, \
<NVR package-1.2.3-4.el6 />]

    >>> sorted(lst)
    [<NVR package-1.2.3-4.el6 />, <NVR package-1.2.3-5.el6 />, \
<NVR package-2.2.3-4.el6 />]
    """
    name = None
    version = None
    release = None

    @staticmethod
    def parse(nvr):
        if isinstance(nvr, NVR):
            # If it's an NVR instance, re-parse to copy
            return NVR.parse(str(nvr))

        if not nvr.strip():
            raise RuntimeError("No NVR to parse: %s" % nvr)
        o = NVR()
        try:
            nvrtuple = re.match("^(^.*)-([^-]*)-([^-]*)$", nvr).groups()
        except:
            raise RuntimeError("Failed to parse NVR: %s" % nvr)
        if not nvrtuple:
            raise RuntimeError("No NVR found: %s" % nvr)
        o.name, o.version, o.release = nvrtuple
        return o

    def __cmp__(self, other):
        assert type(self) == type(other), "%r vs %r" % (self, other)
        if not self.name == other.name:
            raise RuntimeError("NVRs for different names: %s %s"
                               % (self.name, other.name))
        this_version = (None, self.version, self.release)
        other_version = (None, other.version, other.release)
        return rpm.labelCompare(this_version,  # @UndefinedVariable
                                other_version)

    def __str__(self):
        return "%s-%s-%s" % (self.name, self.version, self.release)

    def __repr__(self):
        return "<NVR %s />" % self

    def __hash__(self):
        return hash(str(self))


class Image(object):
    """Representing either a Base or a Layer

    This class is used to build the hierarchy which is implicitly
    defined by the versions and layer indexes of the LVM volumes.
    The volumes are read and transformed into objects of this type.
    These objects are then used to perform several tasks in the
    NvrNaming class, i.e. finding out what the next layer index will be.

    >>> Image.from_nvr("Image-1-2")
    <Base Image-1-2 [] />
    """
    _sep = "+"
    nvr = None

    @classmethod
    def from_nvr(cls, nvr):
        if cls._sep in nvr:
            return Layer(nvr)
        return Base(nvr)

    @property
    def lv_name(self):
        """Provide a LVM safe name for this image

        >>> i = Image.from_nvr("Image-1-2")
        >>> i.lv_name
        'Image-1-2'

        >>> i = Image.from_nvr("Image-1-2+1")
        >>> i.lv_name
        'Image-1-2+1'

        >> i.index = 3
        >> i.lv_name
        'Image-1-2+3'
        """
        name = str(self)
        assert re.search("^[a-zA-Z0-9_.+-]+$", name), \
            "Invalid LV name: %s" % name
        return name

    def __hash__(self):
        return hash(repr(self))

    def __cmp__(self, other):
        return cmp(self.nvr, other.nvr)

    def __str__(self):
        return str(self.nvr)

    def is_base(self):
        return isinstance(self, Base)

    def is_layer(self):
        return isinstance(self, Layer)


class Base(Image):
    """Represents a base

    A convenience function to i.e. get the NVR for a layer on this base
    with a specific index

    >>> Base("Image-0-0")
    <Base Image-0-0 [] />
    """
    layers = None

    def __init__(self, nvr, layers=None):
        assert self._sep not in str(nvr)
        self.nvr = NVR.parse(nvr)  # For convenience: Parse if necessary
        self.layers = layers or []

    def __repr__(self):
        return "<Base %s %s />" % (self.nvr, self.layers)

    def derive_layer(self, index):
        nvr = "%s%s%s" % (self.nvr, self._sep, index)
        return Layer(nvr)


class Layer(Image):
    """Representing a layer, a child of a base (or other layer)

    Convenience class to access the base or create an NVR for
    a specific layer.

    >>> l = Layer("Image-0-0+0")
    >>> l
    <Layer Image-0-0+0 />

    >>> l.nvr
    <NVR Image-0-0+0 />

    >>> l.index
    '0'

    >>> l.index = 1
    >>> l
    <Layer Image-0-0+1 />
    """
    @property
    def index(self):
        return str(self.nvr).rpartition(self._sep)[2]

    @index.setter
    def index(self, index):
        index = str(index)
        assert index.isdigit()
        self.nvr = NVR.parse(str(self.base.nvr) + self._sep + index)

    @property
    def base(self):
        return Base(str(self.nvr).rpartition(self._sep)[0])

    def __init__(self, nvr):
        assert self._sep in str(nvr)
        self.nvr = NVR.parse(nvr)  # For convenience: Parse if necessary

    def __repr__(self):
        return "<Layer %s />" % self.nvr


# vim: sw=4 et sts=4:

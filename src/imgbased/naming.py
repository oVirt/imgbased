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
from .utils import format_to_pattern
from .layers import Base, Layer

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
        assert all(type(b) is Base for b in bases)
        return bases

    def layers(self, for_base=None):
        layers = []
        for b in self.tree():
            if for_base is None or (for_base and b == for_base):
                layers.extend(b.layers)
        return sorted(layers)

    def last_base(self):
        return self.bases().pop()

    def last_layer(self):
        return self.layers().pop()

    def layer_before(self, other_layer):
        layers = self.layers()
        assert other_layer in layers
        oidx = layers.index(other_layer)
        return layers[oidx-1]

    def suggest_next_base(self, name, version=None, release=None):
        """Dertermine the name for the next base LV name (based on the scheme)
        """
        log.debug("Finding next base")
        try:
            base = self.last_base()
            base.version = version or int(base.version) + 1
            base.release = release or 0
            base.layers = []
        except RuntimeError:
            log.debug("No previous base found, creating an initial one")
            base = Base(name, version or 0, release or 0)
        if name:
            base.name = name
        log.debug("Initial base is now: %s" % base)
        return base

    def suggest_next_layer(self, prev):
        """Determine the LV name of the next layer (based on the scheme)

        image: Layer or Base
        """
        suggestion = Layer()

        suggestion.name = prev.name
        suggestion.version = prev.version

        if prev.is_base():
            log.debug("Suggesting for layer for base %s" % prev)
            # FIXME If prev is a freshly generated Layer(), then it
            # has no layers, only images form tree() have layers.
            if prev.layers:
                log.debug("... with layers")
                last_layer = sorted(prev.layers).pop()
                suggestion.release = int(last_layer.release) + 1
            else:
                log.debug("... without layers")
                suggestion.release = 1
        else:
            log.debug("Suggesting for layer for prev layer %s" % prev)
            suggestion.release = int(prev.release) + 1

        return suggestion

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


class NvrLikeNaming(NamingScheme):
    """This class is for parsing nvr like schemes.
    Example: Image-0.0

    >>> layers = NvrLikeNaming([])
    >>> layers.last_base()
    Traceback (most recent call last):
    ...
    RuntimeError: No bases found: []

    >>> names = ["Image-0.0", "Image-13.0", "Image-13.1",
    ... "Image-2.1", "Image-2.0"]
    >>> layers = NvrLikeNaming(names)
    >>> layers.last_base()
    <Base Image-13.0 [<Layer Image-13.1 />]/>

    >>> layers = NvrLikeNaming([])
    >>> layers.last_layer()
    Traceback (most recent call last):
    ...
    RuntimeError: No bases found: []

    >>> names = ["Image-0.0", "Image-13.0", "Image-13.1", "Image-2.0"]
    >>> layers = NvrLikeNaming(names)
    >>> layers.last_layer()
    <Layer Image-13.1 />


    >>> layers = NvrLikeNaming([])
    >>> layers.suggest_next_base(name="Image")
    <Base Image-0.0 />

    >>> names = ["Image-0.0"]
    >>> layers = NvrLikeNaming(names)
    >>> layers.suggest_next_base(name="Image")
    <Base Image-1.0 />

    >>> names = ["Image-0.0", "Image-13.0", "Image-13.1", "Image-2.0",
    ... "Image-0.1", "Image-2.1"]
    >>> layers = NvrLikeNaming(names)
    >>> layers.suggest_next_base(name="Image")
    <Base Image-14.0 />
    >>> layers.suggest_next_base("Image", version=20140401)
    <Base Image-20140401.0 />

    >>> layers.layers()
    [<Layer Image-0.1 />, <Layer Image-2.1 />, <Layer Image-13.1 />]

    >>> layers.layers(for_base=Base("Image", 2, 0))
    [<Layer Image-2.1 />]

    >>> names = ["Image-0.0"]
    >>> layers = NvrLikeNaming(names)
    >>> layers.suggest_next_layer(Layer("Image", "0", "0"))
    <Layer Image-0.1 />

    >>> names = ["Image-0.0", "Image-13.0", "Image-13.1",
    ... "Image-2.0", "Image-2.1"]
    >>> layers = NvrLikeNaming(names)
    >>> layers.suggest_next_layer(Layer("Image", "13", "1"))
    <Layer Image-13.2 />

    >>> layers.suggest_next_layer(Layer("Image", 2, 0))
    <Layer Image-2.1 />


    >>> layers = NvrLikeNaming([])
    >>> print(layers.layout())
    Traceback (most recent call last):
    ...
    RuntimeError: No valid layout found. Initialize if needed.

    >>> names = ["Image-0.0", "Image-13.0", "Image-2.1", "Image-2.0",
    ... "Image-2.2"]
    >>> layers = NvrLikeNaming(names)
    >>> layers.layout()
    'Image-0.0\\nImage-2.0\\n ├╼ Image-2.1\\n └╼ Image-2.2\\nImage-13.0'

    """

    nvr_fmt = "%s-%d.%d"

    def tree(self, datasource=None):
        """Returns a list of bases and children
        >>> layers = NvrLikeNaming([])
        >>> layers.tree()
        Traceback (most recent call last):
        ...
        RuntimeError: No bases found: []

        >>> names = ["Image-0.0", "Image-13.0", "Image-2.1",
        ... "Image-2.0"]
        >>> layers = NvrLikeNaming(names)
        >>> layers.tree()
        [<Base Image-0.0 />, <Base Image-2.0 [<Layer Image-2.1 />]/>, \
<Base Image-13.0 />]
        """
        datasource = datasource or self.datasource
        if callable(datasource):
            names = datasource()
        else:
            names = datasource

        laypat = format_to_pattern(self.nvr_fmt)
        sorted_names = []

        for name in names:
            if not re.match(laypat, name):
                continue
            name, version, release = re.search(laypat, name).groups()
            baseidx, layidx = map(int, [version, release])
            sorted_names.append((name, baseidx, layidx))

        sorted_names = sorted(sorted_names)

        lst = []
        imgs = []
        for v in sorted_names:
            if v[2] == 0:
                img = Base(*v)
            else:
                img = Layer(*v)
            imgs.append(img)
        for img in imgs:
            if img.release == 0:
                lst.append(img)
            else:
                parent = lst[-1]
                parent.layers.append(img)

        if len(lst) == 0:
            raise RuntimeError("No bases found: %s" % names)

        return lst

    def image_from_name(self, name):
        """
        >>> naming = NvrLikeNaming(["Image-1.0", "Image-24.0"])
        >>> naming.image_from_name("Image-1.0")
        <Base Image-1.0 />
        >>> naming.image_from_name("Image-24.0")
        <Base Image-24.0 />
        """
        laypat = format_to_pattern(self.nvr_fmt)
        log.debug("Prasing %s from %s" % (laypat, name))
        match = re.search(laypat, name)
        if not match:
            raise RuntimeError("Failed to parse image name: %s" % name)
        name, version, release = match.groups()
        if int(release) == 0:
            klass = Base
        else:
            klass = Layer
        img = klass(name=str(name), version=int(version),
                    release=int(release))
        if klass == Base:
            img.layers = self.layers(for_base=img)
        return img

# vim: sw=4 et sts=4:

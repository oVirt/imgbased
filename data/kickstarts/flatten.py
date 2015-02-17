#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# flatten
#
# Copyright (C) 2014  Red Hat, Inc.
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
"""
Flatten a ks file, similar to ksflatten, but dump - ignoring unknown directives
"""

import sys
import os


def replace_in_template(template):
    basedir = os.path.dirname(template)
    content = ""
    with open(template) as src:
        for line in src:
            if line.startswith("%include "):
                incl = line.replace("%include ", "").strip()
                content += "\n\n##\n## Including %s\n##\n" % incl
                incl = os.path.join(basedir, incl)
                content += replace_in_template(incl)
            else:
                content += line
    assert content
    return content


if __name__ == "__main__":
    template = sys.argv[1]
    print(replace_in_template(template))

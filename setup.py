# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from setuptools import setup, Extension
from Cython.Build import cythonize
import numpy

ext = Extension(
    "core._convex_hull",
    sources=["core/_convex_hull.pyx"],
    include_dirs=[numpy.get_include()],
)

setup(
    name="ZarinEngine-convex-hull",
    ext_modules=cythonize([ext], language_level="3"),
)

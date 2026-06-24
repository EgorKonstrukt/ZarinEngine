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

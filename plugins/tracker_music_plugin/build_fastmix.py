# Build helper for the tracker fastmix Cython extension.
#
# Usage:
#   python build_fastmix.py            # compile fastmix.pyx -> fastmix.<pyd|so> inplace
#   python build_fastmix.py --check    # exit 0 if importable, 1 otherwise
#   python build_fastmix.py --force    # force rebuild even if up to date
#
# All artifacts stay inside this plugin directory (per project requirement).

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PYX = os.path.join(_HERE, "fastmix.pyx")


def _ext_suffix() -> str:
    import importlib.machinery as _m
    suf = (_m.EXTENSION_SUFFIXES or [".pyd"])[0]
    return suf


def extension_path() -> str:
    for fn in os.listdir(_HERE):
        if fn.startswith("fastmix.") and (
            fn.endswith(".pyd") or fn.endswith(".so")
        ):
            return os.path.join(_HERE, fn)
    return os.path.join(_HERE, "fastmix" + _ext_suffix())


def is_built() -> bool:
    return os.path.isfile(extension_path())


def is_up_to_date() -> bool:
    ext = extension_path()
    if not os.path.isfile(ext) or not os.path.isfile(_PYX):
        return False
    try:
        return os.path.getmtime(ext) >= os.path.getmtime(_PYX)
    except OSError:
        return False


def build_inplace(force: bool = False, quiet: bool = False) -> bool:
    if not os.path.isfile(_PYX):
        print(f"fastmix.pyx not found: {_PYX}", file=sys.stderr)
        return False
    if not force and is_up_to_date():
        if not quiet:
            print(f"fastmix up to date: {extension_path()}")
        return True
    try:
        import numpy  # noqa: F401
    except ImportError:
        print("numpy is required to build fastmix", file=sys.stderr)
        return False
    try:
        from Cython.Build import cythonize  # noqa: F401
    except ImportError:
        print("Cython is required to build fastmix (pip install cython)", file=sys.stderr)
        return False

    # Defer setuptools import so `--check` stays lightweight.
    import numpy as _np
    from Cython.Build import cythonize as _cythonize
    from setuptools import Extension, setup

    ext = Extension(
        "fastmix",
        sources=[_PYX],
        include_dirs=[_np.get_include()],
        define_macros=[("NPY_NO_DEPRECATED_API", "NPY_1_7_API_VERSION")],
    )
    argv_save = sys.argv[:]
    try:
        sys.argv = [sys.argv[0], "build_ext", "--inplace"]
        # Run the build with cwd = plugin dir so the .pyd lands next to .pyx.
        cwd_save = os.getcwd()
        os.chdir(_HERE)
        try:
            setup(
                name="zarin-tracker-fastmix",
                ext_modules=_cythonize(
                    [ext],
                    language_level=3,
                    compiler_directives={
                        "boundscheck": False,
                        "wraparound": False,
                        "cdivision": True,
                        "nonecheck": False,
                        "initializedcheck": False,
                    },
                ),
                script_args=["build_ext", "--inplace"],
            )
        finally:
            os.chdir(cwd_save)
    except SystemExit as e:
        # setup() calls sys.exit(0) on success.
        if e.code not in (None, 0, "0"):
            print(f"fastmix build failed (exit={e.code})", file=sys.stderr)
            return False
    except Exception as e:  # noqa: BLE001
        print(f"fastmix build failed: {e}", file=sys.stderr)
        return False
    finally:
        sys.argv = argv_save
    ok = is_built()
    if not quiet:
        print(f"fastmix build {'OK' if ok else 'FAILED'}: {extension_path()}")
    return ok


def main(argv: list[str]) -> int:
    if "--check" in argv:
        # Importable check without building.
        try:
            sys.path.insert(0, os.path.dirname(_HERE))
            import importlib

            for name in (
                "plugins.tracker_music_plugin.fastmix",
                "tracker_music_plugin.fastmix",
                "fastmix",
            ):
                try:
                    importlib.import_module(name)
                    print(f"fastmix importable as {name}")
                    return 0
                except ImportError:
                    continue
            # Fallback: extension file exists?
            if is_built():
                print(f"fastmix file exists: {extension_path()}")
                return 0
            print("fastmix NOT built", file=sys.stderr)
            return 1
        except Exception as e:  # noqa: BLE001
            print(f"check failed: {e}", file=sys.stderr)
            return 1
    force = "--force" in argv
    ok = build_inplace(force=force)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

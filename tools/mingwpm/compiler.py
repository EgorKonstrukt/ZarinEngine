# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os
import subprocess
import sys
from .toolchain import W64DEVKIT_VERSION
from .toolchain import _ENV_COMPILER
from .toolchain import ensure_mingw
from .toolchain import find_gcc
from .toolchain import toolchain_dir


def pop_compiler_argv(argv: list[str] | None = None) -> str | None:
    if argv is None:
        argv = sys.argv
    choice: str | None = None
    kept: list[str] = []
    skip_next = False
    for i, tok in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        if tok == "--compiler" and i + 1 < len(argv):
            choice = argv[i + 1]
            skip_next = True
            continue
        if tok.startswith("--compiler="):
            choice = tok.split("=", 1)[1]
            continue
        if tok == "--use-mingw":
            choice = "mingw"
            continue
        if tok == "--use-msvc":
            choice = "msvc"
            continue
        kept.append(tok)
    argv[:] = kept
    return choice


def resolve_compiler(explicit: str | None = None) -> str:
    val = (explicit or os.environ.get(_ENV_COMPILER, "auto")).strip().lower()
    if val in ("mingw", "mingw32", "mingw64", "gcc"):
        return "mingw"
    if val in ("msvc", "vs", "visual", "cl"):
        return "msvc"
    if val in ("system", "native", "default"):
        return "system" if sys.platform != "win32" else "mingw"
    return "mingw" if sys.platform == "win32" else "system"


def nuitka_flags(explicit: str | None = None) -> list[str]:
    flags = ["--assume-yes-for-downloads"]
    if sys.platform != "win32":
        return flags
    compiler = resolve_compiler(explicit)
    if compiler == "mingw":
        flags.append("--mingw64")
        if sys.version_info >= (3, 13):
            flags.append("--experimental=force-mingw64")
    elif compiler == "msvc":
        flags.append("--msvc=latest")
    return flags


def status() -> dict:
    gcc = find_gcc()
    info: dict = {
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "compiler": resolve_compiler(),
        "toolchain_dir": str(toolchain_dir()),
        "gcc": str(gcc) if gcc else None,
    }
    if gcc:
        try:
            proc = subprocess.run(
                [str(gcc), "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=30,
            )
            info["gcc_version"] = (proc.stdout or "").splitlines()[0]
        except Exception:
            info["gcc_version"] = "unknown"
    return info


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--ensure" in argv:
        try:
            bin_dir = ensure_mingw()
            print(bin_dir)
            return 0
        except Exception as e:
            print(f"ERROR: {e}")
            return 1
    if "--print-bin" in argv:
        try:
            print(ensure_mingw())
            return 0
        except Exception as e:
            print(f"ERROR: {e}")
            return 1
    if "--print-nuitka-flags" in argv:
        print(" ".join(nuitka_flags()))
        return 0
    info = status()
    print(f"platform:      {info['platform']}")
    print(f"python:        {info['python']}")
    print(f"compiler:      {info['compiler']} (env {_ENV_COMPILER}=auto)")
    print(f"toolchain dir: {info['toolchain_dir']}")
    if info["gcc"]:
        print(f"gcc:           {info['gcc']}")
        print(f"gcc version:   {info.get('gcc_version', '?')}")
    else:
        print("gcc:           NOT FOUND — will auto-download on first build")
        print(f"  (~60 MB w64devkit {W64DEVKIT_VERSION} from github.com/skeeto/w64devkit)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

"""
Automatic, compact MinGW-w64 toolchain for Nuitka and Cython on Windows.

MSVC (Visual Studio Build Tools) weights several gigabytes. Instead we use
a minimal standalone MinGW-w64 distribution:

* w64devkit (https://github.com/skeeto/w64devkit) — ~60 MB download,
  no installation, single folder with gcc/g++/binutils/make.

The toolchain is downloaded once into a per-user cache dir
(``%LOCALAPPDATA%\\Zarin\\mingw64`` on Windows, ``~/.zarin/mingw64``
elsewhere, overridable via the ``ZARIN_MINGW_DIR`` env var) and is shared
between ZarinEngine and ZarinHub, so it is fetched only once.

For Nuitka itself we additionally pass ``--mingw64
--assume-yes-for-downloads`` so Nuitka fetches/uses its own compact
MinGW automatically (fully non-interactive, no MSVC needed). On
Python 3.13+ Nuitka also needs ``--experimental=force-mingw64``.

Usage:
    python tools/mingw.py --check    # report status, no download
    python tools/mingw.py --ensure   # download if missing, print bin dir

API:
    from tools.mingw import (
        ensure_mingw, find_gcc, is_available, env_with_mingw,
        resolve_compiler, nuitka_flags,
    )
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

# Compact, portable MinGW-w64 distribution (~60 MB, single folder).
W64DEVKIT_VERSION = "2.9.1"
W64DEVKIT_URL = (
    "https://github.com/skeeto/w64devkit/releases/download/"
    f"v{W64DEVKIT_VERSION}/w64devkit-x64-{W64DEVKIT_VERSION}.7z.exe"
)
W64DEVKIT_MIN_SIZE = 10 * 1024 * 1024  # sanity check: must be > 10 MB

_ENV_DIR = "ZARIN_MINGW_DIR"
_ENV_COMPILER = "ZARIN_COMPILER"
_ENV_NO_DOWNLOAD = "ZARIN_NO_AUTO_DOWNLOAD"


def toolchain_dir() -> Path:
    """Location of the shared MinGW-w64 toolchain."""
    override = os.environ.get(_ENV_DIR)
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(
            Path.home() / "AppData" / "Local"
        )
        return Path(base) / "Zarin" / "mingw64"
    return Path.home() / ".zarin" / "mingw64"


def _nuitka_cache_roots() -> list[Path]:
    """Places where Nuitka keeps its auto-downloaded MinGW (reused if found)."""
    roots: list[Path] = []
    if sys.platform == "win32":
        for env_key in ("APPDATA", "LOCALAPPDATA"):
            base = os.environ.get(env_key)
            if base:
                roots.append(Path(base) / "Nuitka")
    roots.append(Path.home() / ".cache" / "Nuitka")
    return roots


def _find_gcc_under(root: Path, max_depth: int = 4) -> Path | None:
    """Look for bin/gcc.exe (or bin/gcc) under *root* without deep walks."""
    if not root.is_dir():
        return None
    # Fast paths first.
    for cand in (
        root / "bin" / "gcc.exe",
        root / "bin" / "gcc",
        root / "mingw64" / "bin" / "gcc.exe",
        root / "mingw64" / "bin" / "gcc",
    ):
        if cand.is_file():
            return cand
    # Bounded walk as a fallback.
    root = root.resolve()
    queue: list[tuple[Path, int]] = [(root, 0)]
    while queue:
        cur, depth = queue.pop(0)
        if depth > max_depth:
            continue
        try:
            entries = list(cur.iterdir())
        except OSError:
            continue
        for e in entries:
            if e.is_file() and e.name.lower() in ("gcc.exe", "gcc"):
                if e.parent.name.lower() == "bin":
                    return e
        if depth < max_depth:
            for e in entries:
                if e.is_dir() and not e.is_symlink():
                    if e.name.startswith(".") and e.name not in (".mingw64",):
                        continue
                    queue.append((e, depth + 1))
    return None


def find_gcc() -> Path | None:
    """Return path to a usable gcc, or None.

    Order: our cache dir -> PATH -> Nuitka's auto-downloaded MinGW.
    """
    if sys.platform != "win32":
        found = shutil.which("gcc")
        return Path(found) if found else None
    cached = _find_gcc_under(toolchain_dir(), max_depth=3)
    if cached:
        return cached
    on_path = shutil.which("gcc") or shutil.which("gcc.exe")
    if on_path:
        return Path(on_path)
    for root in _nuitka_cache_roots():
        reused = _find_gcc_under(root, max_depth=4)
        if reused:
            return reused
    return None


def is_available() -> bool:
    """True if a gcc is already usable (no download needed)."""
    return find_gcc() is not None


def bin_dir_for(gcc: Path) -> Path:
    return gcc.parent


def _print_progress(downloaded: int, total: int) -> None:
    if total > 0:
        pct = downloaded * 100 // total
        bar = "#" * (pct // 5) + "-" * (20 - pct // 5)
        sys.stdout.write(
            f"\r  [{bar}] {pct:3d}% "
            f"({downloaded / 1048576:.1f}/{total / 1048576:.1f} MB)"
        )
    else:
        sys.stdout.write(f"\r  downloaded {downloaded / 1048576:.1f} MB")
    sys.stdout.flush()


def _download(url: str, dest: Path) -> None:
    last_exc: Exception | None = None
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "ZarinEngine-mingw-bootstrap/1.0"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp, open(
                dest, "wb"
            ) as f:
                total = int(resp.headers.get("Content-Length", "0") or 0)
                got = 0
                while True:
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    _print_progress(got, total)
            sys.stdout.write("\n")
            if dest.stat().st_size < W64DEVKIT_MIN_SIZE:
                raise IOError(
                    f"downloaded file too small "
                    f"({dest.stat().st_size} bytes) — bad download"
                )
            return
        except Exception as e:  # noqa: BLE001 — retry any failure
            last_exc = e
            print(f"\n  download attempt {attempt}/3 failed: {e}")
            try:
                if dest.exists():
                    dest.unlink()
            except OSError:
                pass
    raise RuntimeError(f"MinGW-w64 download failed: {last_exc}")


def _extract_sfx(exe_path: Path, target: Path) -> bool:
    """Extract the w64devkit self-extracting 7z archive (7z SFX switches)."""
    target.mkdir(parents=True, exist_ok=True)
    attempts = [
        [str(exe_path), "-y", f"-o{target}"],
        [str(exe_path), f"-o{target}", "-y"],
    ]
    for args in attempts:
        try:
            proc = subprocess.run(
                args,
                cwd=str(Path(tempfile.gettempdir())),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=300,
            )
            if _find_gcc_under(target, max_depth=3):
                return True
            out = (proc.stdout or "")[-500:]
            print(f"  extract attempt {' '.join(args[1:])} rc={proc.returncode} {out}")
        except Exception as e:  # noqa: BLE001 — try next variant
            print(f"  extract attempt failed: {e}")
    return _find_gcc_under(target, max_depth=3) is not None


def ensure_mingw(auto_download: bool = True) -> Path:
    """Ensure a MinGW-w64 gcc exists; download w64devkit if needed.

    Returns the toolchain ``bin`` directory. Raises RuntimeError when no
    compiler is available and downloading is disabled/failed.
    """
    found = find_gcc()
    if found:
        print(f"MinGW-w64 found: {found}")
        return bin_dir_for(found)
    if not auto_download or os.environ.get(_ENV_NO_DOWNLOAD) == "1":
        raise RuntimeError(
            "No MinGW-w64 gcc found and automatic download is disabled. "
            f"Install one manually or unset {_ENV_NO_DOWNLOAD}, or set "
            f"{_ENV_DIR} to an existing toolchain."
        )
    if sys.platform != "win32":
        raise RuntimeError(
            "No system gcc found. Install it with your package manager "
            "(e.g. apt install build-essential)."
        )
    target = toolchain_dir()
    print(f"Downloading compact MinGW-w64 (w64devkit {W64DEVKIT_VERSION}, ~60 MB)...")
    print(f"  URL: {W64DEVKIT_URL}")
    print(f"  dir: {target}")
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="zarin_mingw_") as tmp:
        exe_path = Path(tmp) / f"w64devkit-x64-{W64DEVKIT_VERSION}.7z.exe"
        _download(W64DEVKIT_URL, exe_path)
        print("Extracting MinGW-w64...")
        if not _extract_sfx(exe_path, target):
            raise RuntimeError(
                f"Failed to extract MinGW-w64 to {target}. "
                "Download manually from https://github.com/skeeto/w64devkit "
                f"and set {_ENV_DIR} to the extracted folder."
            )
    try:
        (target / ".zarin-toolchain-version").write_text(
            W64DEVKIT_VERSION, encoding="utf-8"
        )
    except OSError:
        pass
    found = find_gcc()
    if not found:
        raise RuntimeError(
            f"MinGW-w64 extraction finished but gcc was not found in {target}."
        )
    _check_gcc(found)
    print(f"MinGW-w64 ready: {found}")
    return bin_dir_for(found)


def _check_gcc(gcc: Path) -> None:
    try:
        proc = subprocess.run(
            [str(gcc), "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30,
        )
        first = (proc.stdout or "").splitlines()
        print(f"  {first[0] if first else 'gcc --version failed'}")
    except Exception as e:  # noqa: BLE001 — informational only
        print(f"  (could not run gcc --version: {e})")


def activate(bin_dir: Path | None = None) -> dict[str, str]:
    """Prepend the toolchain to PATH and set CC/CXX. Returns the env dict."""
    if bin_dir is None:
        gcc = find_gcc()
        if gcc is None:
            raise RuntimeError("No MinGW-w64 available to activate.")
        bin_dir = bin_dir_for(gcc)
    env = dict(os.environ)
    path = env.get("PATH", "")
    if str(bin_dir).lower() not in path.lower():
        env["PATH"] = str(bin_dir) + os.pathsep + path
    # NOTE: bare names on purpose — setuptools runs shlex.split() on CC,
    # which mangles absolute Windows paths with backslashes. The prepended
    # PATH above guarantees these resolve to this toolchain.
    env["CC"] = "gcc"
    env["CXX"] = "g++"
    # Apply to the current process too so in-process builds pick it up.
    os.environ["PATH"] = env["PATH"]
    os.environ["CC"] = env["CC"]
    os.environ["CXX"] = env["CXX"]
    return env


def env_with_mingw() -> dict[str, str]:
    """Env for subprocess builds: ensures + activates the toolchain."""
    bin_dir = ensure_mingw()
    return activate(bin_dir)


def pop_compiler_argv(argv: list[str] | None = None) -> str | None:
    """Pop --compiler=X / --use-mingw / --use-msvc from argv. Returns choice."""
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
    """Resolve which C compiler to use: 'mingw', 'msvc' or 'system'.

    Default on Windows is MinGW-w64 (compact, auto-downloaded) so that the
    multi-gigabyte MSVC is not required. Set ``ZARIN_COMPILER=msvc`` (or
    pass ``--compiler msvc``) to force Visual Studio.
    """
    val = (explicit or os.environ.get(_ENV_COMPILER, "auto")).strip().lower()
    if val in ("mingw", "mingw32", "mingw64", "gcc"):
        return "mingw"
    if val in ("msvc", "vs", "visual", "cl"):
        return "msvc"
    if val in ("system", "native", "default"):
        return "system" if sys.platform != "win32" else "mingw"
    # "auto" and anything unknown:
    return "mingw" if sys.platform == "win32" else "system"


def nuitka_flags(explicit: str | None = None) -> list[str]:
    """Nuitka CLI flags for automatic, non-interactive MinGW-w64 builds."""
    flags = ["--assume-yes-for-downloads"]
    if sys.platform != "win32":
        return flags
    compiler = resolve_compiler(explicit)
    if compiler == "mingw":
        flags.append("--mingw64")
        if sys.version_info >= (3, 13):
            # Nuitka's MinGW backend needs an opt-in on 3.13+.
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
        except Exception as e:  # noqa: BLE001
            print(f"ERROR: {e}")
            return 1
    if "--print-bin" in argv:
        try:
            print(ensure_mingw())
            return 0
        except Exception as e:  # noqa: BLE001
            print(f"ERROR: {e}")
            return 1
    if "--print-nuitka-flags" in argv:
        print(" ".join(nuitka_flags()))
        return 0
    # Default: --check, no download.
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

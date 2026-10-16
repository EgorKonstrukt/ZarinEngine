# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

W64DEVKIT_VERSION = "2.9.1"
W64DEVKIT_URL = (
    "https://github.com/skeeto/w64devkit/releases/download/"
    f"v{W64DEVKIT_VERSION}/w64devkit-x64-{W64DEVKIT_VERSION}.7z.exe"
)
W64DEVKIT_MIN_SIZE = 10 * 1024 * 1024
_ENV_DIR = "ZARIN_MINGW_DIR"
_ENV_COMPILER = "ZARIN_COMPILER"
_ENV_NO_DOWNLOAD = "ZARIN_NO_AUTO_DOWNLOAD"


def toolchain_dir() -> Path:
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
    roots: list[Path] = []
    if sys.platform == "win32":
        for env_key in ("APPDATA", "LOCALAPPDATA"):
            base = os.environ.get(env_key)
            if base:
                roots.append(Path(base) / "Nuitka")
    roots.append(Path.home() / ".cache" / "Nuitka")
    return roots


def _find_gcc_under(root: Path, max_depth: int = 4) -> Path | None:
    if not root.is_dir():
        return None
    for cand in (
        root / "bin" / "gcc.exe",
        root / "bin" / "gcc",
        root / "mingw64" / "bin" / "gcc.exe",
        root / "mingw64" / "bin" / "gcc",
    ):
        if cand.is_file():
            return cand
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


_GCC_CACHE_TTL = 30.0
_GCC_CACHE_KEY = None
_GCC_CACHE_VALUE = None
_GCC_CACHE_AT = 0.0


def find_gcc() -> Path | None:
    global _GCC_CACHE_KEY, _GCC_CACHE_VALUE, _GCC_CACHE_AT
    try:
        now = time.monotonic()
    except Exception:
        now = 0.0
    try:
        key = (os.environ.get(_ENV_DIR), os.environ.get("PATH", ""))
    except Exception:
        key = (None, "")
    if _GCC_CACHE_KEY == key and _GCC_CACHE_VALUE is not None:
        try:
            if _GCC_CACHE_VALUE.is_file():
                return _GCC_CACHE_VALUE
        except Exception:
            pass
        _GCC_CACHE_KEY = None
        _GCC_CACHE_VALUE = None
        _GCC_CACHE_AT = 0.0
    elif _GCC_CACHE_KEY == key and _GCC_CACHE_VALUE is None:
        try:
            if (now - _GCC_CACHE_AT) < _GCC_CACHE_TTL:
                return None
        except Exception:
            pass
    found = _find_gcc_uncached()
    _GCC_CACHE_KEY = key
    _GCC_CACHE_VALUE = found
    _GCC_CACHE_AT = now
    return found


def _find_gcc_uncached() -> Path | None:
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
    return find_gcc() is not None


def bin_dir_for(gcc: Path) -> Path:
    return gcc.parent


def _print_progress(downloaded: int, total: int) -> None:
    if total > 0:
        pct = downloaded * 100 // total
        bar = chr(35) * (pct // 5) + "-" * (20 - pct // 5)
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
        except Exception as e:
            last_exc = e
            print(f"\n  download attempt {attempt}/3 failed: {e}")
            try:
                if dest.exists():
                    dest.unlink()
            except OSError:
                pass
    raise RuntimeError(f"MinGW-w64 download failed: {last_exc}")


def _extract_sfx(exe_path: Path, target: Path) -> bool:
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
        except Exception as e:
            print(f"  extract attempt failed: {e}")
    return _find_gcc_under(target, max_depth=3) is not None


def ensure_mingw(auto_download: bool = True) -> Path:
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
    except Exception as e:
        print(f"  (could not run gcc --version: {e})")


def activate(bin_dir: Path | None = None) -> dict[str, str]:
    if bin_dir is None:
        gcc = find_gcc()
        if gcc is None:
            raise RuntimeError("No MinGW-w64 available to activate.")
        bin_dir = bin_dir_for(gcc)
    env = dict(os.environ)
    path = env.get("PATH", "")
    if str(bin_dir).lower() not in path.lower():
        env["PATH"] = str(bin_dir) + os.pathsep + path
    env["CC"] = "gcc"
    env["CXX"] = "g++"
    os.environ["PATH"] = env["PATH"]
    os.environ["CC"] = env["CC"]
    os.environ["CXX"] = env["CXX"]
    return env


def env_with_mingw() -> dict[str, str]:
    bin_dir = ensure_mingw()
    return activate(bin_dir)

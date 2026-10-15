# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tools.zplug.pack import build_zplugin
from tools.zplug.verify import _ed_gen
from tools.zplug.verify import _hash_file
from tools.zplug.verify import _hash_zip_member
from tools.zplug.verify import _PM_OK
from tools.zplug.verify import lint_manifest

def _venv_site_packages(venv=None, python_exe=None) -> str:
    exe = python_exe
    if not exe and venv:
        cand = os.path.join(venv, "Scripts", "python.exe")
        if not os.path.isfile(cand):
            cand = os.path.join(venv, "bin", "python")
        exe = cand
    if not exe or not os.path.isfile(exe):
        raise ValueError("venv python not found (pass --venv or --python)")
    result = subprocess.run([exe, "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"could not query site-packages: {(result.stderr or '').strip()[-300:]}")
    path = result.stdout.strip().splitlines()[-1]
    if not os.path.isdir(path):
        raise RuntimeError(f"site-packages not found: {path}")
    return path

def _receipts_dir(site_packages: str) -> str:
    d = os.path.join(site_packages, "zplugin_receipts")
    os.makedirs(d, exist_ok=True)
    return d

def install_pack(archive: str, venv=None, python_exe=None, force: bool = False):
    try:
        import tempfile as _tf
        site_packages = _venv_site_packages(venv, python_exe)
        with zipfile.ZipFile(archive) as zf:
            mname = next((n for n in zf.namelist() if n.endswith("manifest.json")), None)
            if mname is None:
                return (False, "archive has no manifest.json")
            manifest = json.loads(zf.open(mname).read().decode("utf-8"))
            members = [n for n in zf.namelist()
                       if not n.endswith("/") and n != mname and not n.endswith(".zpl_meta.json")]
            if not members:
                return (False, "nothing installable (empty payload)")
            clashes = []
            for member in members:
                rel = member[len("libs/"):] if member.startswith("libs/") else member
                target = os.path.join(site_packages, rel.replace("/", os.sep))
                if os.path.isfile(target):
                    try:
                        if _hash_file(target) != _hash_zip_member(zf, member):
                            clashes.append(rel.replace("/", os.sep))
                    except Exception:
                        clashes.append(rel.replace("/", os.sep))
            if clashes and not force:
                shown = ", ".join(clashes[:5])
                more = f" (+{len(clashes) - 5} more)" if len(clashes) > 5 else ""
                return (False, f"refusing to overwrite {len(clashes)} differing files "
                               f"(use --force): {shown}{more}")
            installed = []
            overwrote = 0
            for member in members:
                rel = member[len("libs/"):] if member.startswith("libs/") else member
                target = os.path.join(site_packages, rel.replace("/", os.sep))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                if os.path.isfile(target):
                    overwrote += 1
                with zf.open(member) as srcf, open(target, "wb") as dstf:
                    shutil.copyfileobj(srcf, dstf)
                installed.append(rel.replace("/", os.sep))
            receipt = {"name": manifest.get("name", ""), "version": manifest.get("version", ""),
                       "archive": os.path.basename(archive), "files": sorted(installed)}
            with open(os.path.join(_receipts_dir(site_packages), receipt["name"] + ".json"),
                      "w", encoding="utf-8") as f:
                json.dump(receipt, f, indent=2)
            msg = f"{len(installed)} files -> {site_packages}"
            if overwrote:
                msg += f" ({overwrote} overwrote existing files)"
            return (True, msg)
    except Exception as e:
        return (False, str(e))

def uninstall_pack(name: str, venv=None, python_exe=None):
    try:
        site_packages = _venv_site_packages(venv, python_exe)
        receipt_path = os.path.join(_receipts_dir(site_packages), name + ".json")
        if not os.path.isfile(receipt_path):
            return (False, f"no install receipt for '{name}'")
        with open(receipt_path, encoding="utf-8") as f:
            receipt = json.load(f)
        removed, missing = 0, 0
        tops = set()
        for rel in receipt.get("files", []):
            target = os.path.join(site_packages, rel)
            tops.add(rel.split(os.sep)[0])
            try:
                if os.path.isfile(target):
                    os.remove(target)
                    removed += 1
                else:
                    missing += 1
            except Exception:
                missing += 1
        for top in sorted(tops):
            tdir = os.path.join(site_packages, top)
            for root, _dirs, _files in os.walk(tdir, topdown=False):
                if os.path.basename(root) == "__pycache__":
                    shutil.rmtree(root, ignore_errors=True)
            for root, dirs, files in os.walk(tdir, topdown=False):
                if not dirs and not files:
                    try:
                        os.rmdir(root)
                    except Exception:
                        pass
            try:
                os.rmdir(tdir)
            except Exception:
                pass
        try:
            os.remove(receipt_path)
        except Exception:
            pass
        return (True, f"removed {removed} files ({missing} already gone)")
    except Exception as e:
        return (False, str(e))

def list_installed_packs(venv=None, python_exe=None) -> list:
    try:
        site_packages = _venv_site_packages(venv, python_exe)
        d = os.path.join(site_packages, "zplugin_receipts")
        out = []
        if os.path.isdir(d):
            for fname in sorted(os.listdir(d)):
                if fname.endswith(".json"):
                    try:
                        with open(os.path.join(d, fname), encoding="utf-8") as f:
                            out.append(json.load(f))
                    except Exception:
                        pass
        return out
    except Exception:
        return []

def _main_manage(cmd, argv) -> int:
    parser = argparse.ArgumentParser(description=f"zplugin {cmd}")
    if cmd == "install":
        parser.add_argument("archive", help="Path to .zplugin file")
    elif cmd == "uninstall":
        parser.add_argument("name", help="Installed pack name")
    parser.add_argument("--venv", default="", help="Target venv directory")
    parser.add_argument("--python", default="", help="Target venv python executable")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite files whose content differs (install only)")
    args = parser.parse_args(argv)
    if cmd == "install":
        ok, msg = install_pack(args.archive, venv=args.venv or None,
                               python_exe=args.python or None, force=args.force)
        print(("OK: " if ok else "Error: ") + msg)
        return 0 if ok else 1
    if cmd == "uninstall":
        ok, msg = uninstall_pack(args.name, venv=args.venv or None, python_exe=args.python or None)
        print(("OK: " if ok else "Error: ") + msg)
        return 0 if ok else 1
    for pack in list_installed_packs(venv=args.venv or None, python_exe=args.python or None):
        print(f"{pack.get('name', '?')} {pack.get('version', '')} ({pack.get('archive', '')})")
    return 0

def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("install", "uninstall", "list"):
        sys.exit(_main_manage(sys.argv[1], sys.argv[2:]))
    parser = argparse.ArgumentParser(description="Build a .zplugin distributable archive")
    parser.add_argument("plugin", nargs="?", help="Path to plugin package directory")
    parser.add_argument("--output", "-o", default="dist", help="Output directory")
    parser.add_argument("--mode", choices=["source", "cython", "nuitka"], default="source",
                        help="Build mode (default: source)")
    parser.add_argument("--lint", action="store_true", help="Validate the manifest and exit")
    parser.add_argument("--genkey", action="store_true", help="Generate an ed25519 key pair and exit")
    parser.add_argument("--bundle", default="",
                        help="Comma-separated third-party modules to vendor into libs/")
    parser.add_argument("--sign-key", default="", help="Hex private key for manifest signing")
    parser.add_argument("--type", choices=["plugin", "library"], default=None,
                        help="Override the manifest type")
    parser.add_argument("--no-freeze", action="store_true", help="Skip the file hash index")
    parser.add_argument("--download", action="store_true",
                        help="Download the dependency closure (manifest 'download' section) instead of using installed packages")
    parser.add_argument("--download-requires", default="",
                        help="Comma-separated requirements to download and vendor (implies --download)")
    parser.add_argument("--python-version", default="", help="Target python version for download (e.g. 3.13)")
    parser.add_argument("--platform", default="", help="Target platform for download (e.g. win_amd64)")
    parser.add_argument("--abi", default="", help="Target ABI for download (e.g. cp313)")
    parser.add_argument("--implementation", default="cp", help="Target implementation for download")
    parser.add_argument("--exclude-mod", action="append", default=[],
                        help="Top-level module to exclude from vendored wheels (repeatable)")
    args = parser.parse_args()
    if args.genkey:
        if not _PM_OK:
            print("Error: key generation needs core.foundation.ed25519; run from the engine root.")
            sys.exit(1)
        priv, pub = _ed_gen()
        print(f"private: {priv}")
        print(f"public:  {pub}")
        sys.exit(0)
    if not args.plugin:
        parser.print_usage()
        sys.exit(2)
    if args.lint:
        errors = lint_manifest(args.plugin)
        if errors:
            for e in errors:
                print(f"lint: {e}")
            sys.exit(1)
        print("manifest OK")
        sys.exit(0)
    try:
        dl_reqs = [m for m in args.download_requires.split(",") if m.strip()]
        triple = {k: v for k, v in
                  (("python_version", args.python_version), ("platform", args.platform),
                   ("abi", args.abi), ("implementation", args.implementation)) if v}
        result = build_zplugin(args.plugin, args.output, args.mode,
                               bundle=[m for m in args.bundle.split(",") if m.strip()],
                               sign_key=args.sign_key, ptype=args.type,
                               freeze=not args.no_freeze,
                               download=args.download or bool(dl_reqs),
                               download_requires=dl_reqs or None,
                               target=triple or None,
                               exclude=args.exclude_mod)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    sys.exit(0 if result else 1)

if __name__ == "__main__":
    main()

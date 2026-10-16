# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

import datetime
import os
import platform
import re
import subprocess
import sys
ENGINE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ENGINE_ROOT)
def mod_version(name):
    try:
        m = __import__(name)
        v = str(getattr(m, "__version__", "") or "")
        if v:
            return v
    except Exception:
        return ""
    if name == "PySide6":
        try:
            from PySide6.QtCore import qVersion
            return str(qVersion())
        except Exception:
            pass
    return ""
def git_info():
    commit, branch = "", ""
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ENGINE_ROOT,
                                capture_output=True, text=True, timeout=15).stdout.strip()
    except Exception:
        pass
    try:
        branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ENGINE_ROOT,
                                capture_output=True, text=True, timeout=15).stdout.strip()
    except Exception:
        pass
    return commit, branch
def ram_gb():
    try:
        import psutil
        return str(round(psutil.virtual_memory().total / (1024 ** 3), 1))
    except Exception:
        return ""
ARCH_TABLE = [
    ("RTX 50", "Blackwell"), ("RTX 40", "Ada Lovelace"), ("RTX 30", "Ampere"),
    ("RTX 20", "Turing"), ("GTX 16", "Turing"), ("GTX 10", "Pascal"),
    ("GTX 9", "Maxwell"), ("GTX 7", "Kepler"), ("GTX 6", "Kepler"),
    ("GTX 5", "Fermi"), ("GTX 4", "Fermi"), ("RX 79", "RDNA3"), ("RX 77", "RDNA3"),
    ("RX 76", "RDNA3"), ("RX 69", "RDNA2"), ("RX 68", "RDNA2"), ("RX 67", "RDNA2"),
    ("RX 66", "RDNA2"), ("RX 65", "RDNA2"), ("RX 64", "RDNA2"), ("RX 59", "RDNA1"),
    ("RX 57", "RDNA1"), ("RX 56", "RDNA1"), ("RX 55", "RDNA1"), ("RX 58", "GCN Polaris"),
    ("RX 5", "GCN Polaris"), ("RX 4", "GCN Polaris"), ("RADEON VII", "Vega"),
    ("VEGA", "Vega"), ("ARC", "Xe-HPG"), ("IRIS XE", "Xe-LP"), ("UHD", "Gen9.5"),
    ("HD GRAPHICS", "Gen9"), ("RADEON 780M", "RDNA3 iGPU"), ("RADEON 660M", "RDNA2 iGPU"),
    ("RADEON 610M", "RDNA2 iGPU"), ("VEGA 8", "Vega iGPU"), ("VEGA 11", "Vega iGPU"),
]
def detect_arch(gpu_name, override):
    if override:
        return override
    u = (gpu_name or "").upper()
    for key, arch in ARCH_TABLE:
        if key in u:
            return arch
    return ""
def wmic_gpus():
    pairs = []
    try:
        out = subprocess.run(["wmic", "path", "win32_VideoController", "get", "Name,DriverVersion", "/format:list"],
                             capture_output=True, text=True, timeout=20).stdout
        name, ver = "", ""
        for ln in out.splitlines():
            s = ln.strip()
            if s.startswith("Name="):
                name = s[5:].strip()
            elif s.startswith("DriverVersion="):
                ver = s[14:].strip()
                if name or ver:
                    pairs.append((name, ver))
                name, ver = "", ""
    except Exception:
        pass
    return pairs
def driver_version(gpu_name):
    u = (gpu_name or "").lower()
    if "nvidia" in u:
        try:
            out = subprocess.run(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                                 capture_output=True, text=True, timeout=20).stdout
            v = out.strip().splitlines()[0].strip() if out.strip() else ""
            if v:
                return v
        except Exception:
            pass
    if platform.system() == "Windows":
        pairs = wmic_gpus()
        if pairs:
            short = re.sub(r"[^A-Z0-9 ]", "", u.upper())
            for name, ver in pairs:
                if name and any(tok in name.upper() for tok in short.split() if len(tok) > 2):
                    return ver
            return pairs[0][1]
    return ""
def gl_info():
    info = {"renderer": "", "version": ""}
    try:
        import moderngl
        ctx = moderngl.create_standalone_context(require=330)
        try:
            d = dict(ctx.info)
            info["renderer"] = str(d.get("GL_RENDERER", ""))
            info["version"] = str(d.get("GL_VERSION", ""))
        except Exception:
            pass
        try:
            ctx.release()
        except Exception:
            pass
    except Exception as e:
        info["error"] = str(e)[:200]
    return info
def cpu_label():
    try:
        import psutil
        return platform.machine() + ", " + str(psutil.cpu_count(logical=True)) + " cores"
    except Exception:
        return platform.machine()
def collect_env(args):
    commit, branch = git_info()
    g = gl_info()
    gpu = g.get("renderer", "")
    return {
        "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "tester": args.tester,
        "machine": platform.node(),
        "gpu": gpu,
        "arch": detect_arch(gpu, args.arch),
        "driver": driver_version(gpu),
        "os": platform.system() + " " + platform.release(),
        "cpu": cpu_label(),
        "ram": ram_gb(),
        "commit": commit,
        "branch": branch,
        "python": platform.python_version(),
        "pyside": mod_version("PySide6"),
        "moderngl": mod_version("moderngl"),
        "scene": args.scene,
        "gl_error": g.get("error", ""),
    }
def shader_blocks():
    found = []
    root = os.path.join(ENGINE_ROOT, "core", "shaders")
    for dp, dn, fn in os.walk(root):
        for f in sorted(fn):
            if f.endswith(".shader"):
                p = os.path.join(dp, f)
                try:
                    text = open(p, encoding="utf-8", errors="replace").read()
                except Exception:
                    continue
                for bi, m in enumerate(re.finditer(r"GLSLPROGRAM(.*?)ENDGLSL", text, re.DOTALL)):
                    parts = m.group(1).split("// @FRAGMENT")
                    if len(parts) == 2:
                        found.append((os.path.relpath(p, ENGINE_ROOT), bi, parts[0].strip(), parts[1].strip()))
    return found
def load_includes():
    inc = {}
    d = os.path.join(ENGINE_ROOT, "core", "shaders", "include")
    for name in ["area_shadows.glsl", "caustics.glsl"]:
        try:
            inc[name] = open(os.path.join(d, name), encoding="utf-8").read()
        except Exception:
            inc[name] = ""
    return inc
def run_checks(env):
    rows = []
    try:
        import moderngl
        ctx = moderngl.create_standalone_context(require=430)
    except Exception as e:
        rows.append(("Shaders", "GL context available", "standalone context", str(e)[:120], "FAIL"))
        return rows
    inc = load_includes()
    blocks = shader_blocks()
    fails = []
    for rel, bi, vert, frag in blocks:
        frag_f = frag.replace("// @SHADOW_INCLUDE", inc["area_shadows.glsl"]).replace("// @CAUSTICS_INCLUDE", inc["caustics.glsl"])
        try:
            prog = ctx.program(vertex_shader=vert, fragment_shader=frag_f)
            prog.release()
        except Exception as e:
            msg = str(e).splitlines()
            fails.append(rel + " block " + str(bi) + ": " + (msg[2] if len(msg) > 2 else msg[0])[:160])
    rows.append(("Shaders", "Compile all .shader blocks (GLSL 430)",
                 "0 failures", str(len(fails)) + " failures" + (": " + "; ".join(fails[:3]) if fails else ""),
                 "PASS" if not fails else "FAIL"))
    try:
        from core.renderer.shaderp import downgrade_to_330
        fails330 = []
        skipped330 = []
        for rel, bi, vert, frag in blocks:
            has_ssbo = bool(re.search(r"\bbuffer\s+\w+\s*\{", vert)) or bool(re.search(r"\bbuffer\s+\w+\s*\{", frag))
            frag_f = frag.replace("// @SHADOW_INCLUDE", inc["area_shadows.glsl"]).replace("// @CAUSTICS_INCLUDE", inc["caustics.glsl"])
            try:
                prog = ctx.program(vertex_shader=downgrade_to_330(vert).strip(),
                                   fragment_shader=downgrade_to_330(frag_f).strip())
                prog.release()
            except Exception:
                if has_ssbo:
                    skipped330.append(os.path.basename(rel))
                else:
                    fails330.append(rel + " block " + str(bi))
        actual = str(len(fails330)) + " failures" + (": " + "; ".join(fails330[:3]) if fails330 else "")
        if skipped330:
            actual += " | by-design skips (need GL 4.3+ SSBO): " + ", ".join(sorted(set(skipped330)))
        rows.append(("Shaders", "Compile 330-downgrade path", "0 failures",
                     actual, "PASS" if not fails330 else "FAIL"))
    except Exception as e:
        rows.append(("Shaders", "Compile 330-downgrade path", "0 failures", "harness: " + str(e)[:120], "SKIP"))
    over = []
    for rel, bi, vert, frag in blocks:
        samps = re.findall(r"uniform\s+sampler\w+\s+(\w+)(?:\s*\[([^\]]*)\])?\s*;", frag)
        total = 0
        for n, sz in samps:
            if sz:
                sz = sz.strip()
                if "POINT" in sz:
                    total += 24
                elif "SPOT" in sz:
                    total += 4
                else:
                    try:
                        total += int(sz)
                    except Exception:
                        total += 0
            else:
                total += 1
        if total > 16:
            over.append(rel + " block " + str(bi) + " (" + str(total) + ")")
    rows.append(("Shaders", "Fragment sampler budget <= 16 (RX580 rule)", "all fit",
                 "over: " + "; ".join(over) if over else "max fits",
                 "PASS" if not over else "FAIL"))
    dyn = []
    for rel, bi, vert, frag in blocks:
        names = [n for n, sz in re.findall(r"uniform\s+sampler\w+\s+(\w+)\s*\[([^\]]*)\]\s*;", frag)]
        for name in names:
            for i, ln in enumerate(frag.splitlines(), 1):
                s = ln.strip()
                if s.startswith("uniform"):
                    continue
                m = re.search(re.escape(name) + r"\[([^\]]*)\]", s)
                if m and not re.fullmatch(r"\d+", m.group(1).strip()):
                    dyn.append(rel + ":" + str(i) + " " + name + "[" + m.group(1).strip() + "]")
    rows.append(("Shaders", "No dynamic sampler-array indexing (AMD rule)", "none found",
                 str(len(dyn)) + " sites" + (": " + "; ".join(dyn[:3]) if dyn else ""),
                 "PASS" if not dyn else "FAIL"))
    try:
        from core.assets.matp import Material
        bad = []
        n = 0
        for dp, dn, fn in os.walk(os.path.join(ENGINE_ROOT, "assets")):
            for f in sorted(fn):
                if f.endswith((".zpem", ".mat")):
                    p = os.path.join(dp, f)
                    n += 1
                    try:
                        data = open(p, encoding="utf-8").read()
                        sp = re.search(r'"shader_path"\s*:\s*"([^"]*)"', data)
                        if sp and sp.group(1) not in ("", "default"):
                            r = Material._resolve_shader_path(sp.group(1), ENGINE_ROOT)
                            if not os.path.exists(r):
                                bad.append(os.path.basename(p))
                    except Exception:
                        bad.append(os.path.basename(p) + " (read)")
        rows.append(("Assets", "Bundled material shader paths resolve", "0 broken",
                     str(len(bad)) + " broken of " + str(n) + (": " + "; ".join(bad[:3]) if bad else ""),
                     "PASS" if not bad else "FAIL"))
    except Exception as e:
        rows.append(("Assets", "Bundled material shader paths resolve", "0 broken", "harness: " + str(e)[:120], "SKIP"))
    try:
        g = open(os.path.join(ENGINE_ROOT, "core", "shaders", "internal", "Grid.shader"), encoding="utf-8").read()
        ok = bool(re.search(r"smoothstep\([^)]*dens\)", g))
        rows.append(("Grid", "LOD fade guard present in Grid.shader", "present", "present" if ok else "missing", "PASS" if ok else "FAIL"))
    except Exception as e:
        rows.append(("Grid", "LOD fade guard present in Grid.shader", "present", "harness: " + str(e)[:120], "SKIP"))
    try:
        d = open(os.path.join(ENGINE_ROOT, "core", "shaders", "internal", "Default.shader"), encoding="utf-8").read()
        ok = ("u_point_shadow_atlas" in d) and ("u_cascade_atlas" in d)
        rows.append(("Shadows", "Atlas samplers present in Default.shader", "present", "present" if ok else "missing", "PASS" if ok else "FAIL"))
    except Exception as e:
        rows.append(("Shadows", "Atlas samplers present in Default.shader", "present", "harness: " + str(e)[:120], "SKIP"))
    try:
        ctx.release()
    except Exception:
        pass
    return rows

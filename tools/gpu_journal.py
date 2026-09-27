import argparse
import datetime
import json
import os
import platform
import re
import subprocess
import sys
ENGINE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ENGINE_ROOT)
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
RUNS_HEADERS = ["RunID", "Date", "Tester", "Machine", "GPU", "Arch", "Driver", "OS",
                "CPU", "RAM_GB", "Engine_Commit", "Branch", "Python", "PyQt", "moderngl",
                "Scene", "FPS_avg", "FPS_1pct", "FPS_min", "Result", "Issues", "Log", "Notes"]
CHECKS_HEADERS = ["RunID", "Area", "Check", "Expected", "Actual", "Status"]
GPUS_HEADERS = ["GPU", "Vendor", "Arch", "VRAM", "Machine", "Driver_Pinned", "OS", "Owner", "Status", "Notes"]
SCENES_HEADERS = ["Scene", "Path", "Purpose", "Min_FPS_Target"]
FLEET = [
    ["RTX 3090", "NVIDIA", "Ampere", "24GB", "", "", "Windows", "", "Owned", "Reference rig, everything must pass here"],
    ["Radeon RX 580", "AMD", "GCN Polaris", "8GB", "", "", "Windows", "", "Owned", "Strict GLSL compiler, catches sampler/index bugs"],
    ["GTX 1050 Ti", "NVIDIA", "Pascal", "4GB", "", "", "Windows", "", "Planned", "Mass-market floor, perf and VRAM pressure"],
    ["RX 5500 XT", "AMD", "RDNA1", "4/8GB", "", "", "Windows", "", "Planned", "Second AMD compiler backend"],
    ["UHD 630", "Intel", "Gen9.5", "shared", "", "", "Windows", "", "Planned", "Weakest GL compliance, scrap office PC is fine"],
    ["Arc A380", "Intel", "Xe-HPG", "6GB", "", "", "Windows", "", "Planned", "Young driver stack, new bug classes"],
]
SCENES_SEED = [
    ["grid_empty", "", "Grid rendering, LOD fade, no shimmer", "60"],
    ["sun_floor", "", "Directional shadows, cascades, atlas sampling", "60"],
    ["lights_torture", "", "Point and spot shadows, sampler budget under load", "30"],
]
HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(bold=True, color="FFFFFF")
THIN = Side(style="thin", color="B0B0B0")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
def mod_version(name):
    try:
        m = __import__(name)
        v = str(getattr(m, "__version__", "") or "")
        if v:
            return v
    except Exception:
        return ""
    if name == "PyQt6":
        try:
            from PyQt6.QtCore import QT_VERSION_STR
            return str(QT_VERSION_STR)
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
        "pyqt": mod_version("PyQt6"),
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
        from core.renderer.shaders import downgrade_to_330
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
        from core.assets.material import Material
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
def style_sheet(ws, headers, widths):
    ws.append(headers)
    for c in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
        ws.column_dimensions[get_column_letter(c)].width = widths[c - 1]
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    ws.sheet_properties.pageSetUpPr = None
def add_validation(ws, col_letter, formula, start_row=2, end_row=5000):
    dv = DataValidation(type="list", formula1=formula, allow_blank=True)
    dv.error = "Pick from the list"
    dv.errorTitle = "Invalid value"
    ws.add_data_validation(dv)
    dv.add(col_letter + str(start_row) + ":" + col_letter + str(end_row))
def ensure_workbook(path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Runs"
    style_sheet(ws, RUNS_HEADERS, [8, 16, 14, 14, 28, 14, 22, 16, 28, 8, 14, 8, 8, 8, 10, 18, 9, 9, 9, 10, 20, 20, 30])
    add_validation(ws, "T", '"PASS,FAIL,BLOCKED"')
    ws2 = wb.create_sheet("Checks")
    style_sheet(ws2, CHECKS_HEADERS, [8, 16, 44, 30, 60, 10])
    add_validation(ws2, "F", '"PASS,FAIL,SKIP"')
    ws3 = wb.create_sheet("GPUs")
    style_sheet(ws3, GPUS_HEADERS, [22, 10, 14, 8, 14, 18, 12, 12, 10, 40])
    for row in FLEET:
        ws3.append(row)
    for r in range(2, 2 + len(FLEET)):
        for c in range(1, len(GPUS_HEADERS) + 1):
            ws3.cell(row=r, column=c).border = BORDER
    add_validation(ws3, "I", '"Owned,Planned,Retired"')
    ws4 = wb.create_sheet("Scenes")
    style_sheet(ws4, SCENES_HEADERS, [24, 40, 52, 14])
    for row in SCENES_SEED:
        ws4.append(row)
    for r in range(2, 2 + len(SCENES_SEED)):
        for c in range(1, len(SCENES_HEADERS) + 1):
            ws4.cell(row=r, column=c).border = BORDER
    wb.save(path)
    return path
def append_run(path, env, rows):
    wb = load_workbook(path)
    ws = wb["Runs"]
    run_id = 1
    for r in range(2, ws.max_row + 1):
        v = ws.cell(row=r, column=1).value
        if isinstance(v, int) and v >= run_id:
            run_id = v + 1
    record = [run_id, env["date"], env["tester"], env["machine"], env["gpu"], env["arch"],
              env["driver"], env["os"], env["cpu"], env["ram"], env["commit"], env["branch"],
              env["python"], env["pyqt"], env["moderngl"], env["scene"], "", "", "",
              "FAIL" if any(s == "FAIL" for _, _, _, _, s in rows) else "PASS",
              "", "", ""]
    ws.append(record)
    for c in range(1, len(record) + 1):
        ws.cell(row=ws.max_row, column=c).border = BORDER
    for c in [7, 11, 12, 13, 14, 15]:
        ws.cell(row=ws.max_row, column=c).number_format = "@"
    ws2 = wb["Checks"]
    for area, name, exp, act, status in rows:
        ws2.append([run_id, area, name, exp, act, status])
        for c in range(1, 7):
            ws2.cell(row=ws2.max_row, column=c).border = BORDER
    wb.save(path)
    return run_id
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tester", default="")
    ap.add_argument("--machine", default="")
    ap.add_argument("--arch", default="")
    ap.add_argument("--scene", default="")
    ap.add_argument("--journal", default=os.path.join(ENGINE_ROOT, "tests", "TestJournal.xlsx"))
    ap.add_argument("--no-save", action="store_true")
    args = ap.parse_args()
    env = collect_env(args)
    if args.machine:
        env["machine"] = args.machine
    print("GPU: " + (env["gpu"] or "?") + " | driver: " + (env["driver"] or "?") + " | commit: " + (env["commit"] or "?"))
    if env["gl_error"]:
        print("GL unavailable: " + env["gl_error"])
    rows = run_checks(env)
    for area, name, exp, act, status in rows:
        print("[" + status + "] " + area + " / " + name + " :: " + act)
    if not args.no_save:
        if not os.path.exists(args.journal):
            ensure_workbook(args.journal)
            print("journal created: " + args.journal)
        try:
            run_id = append_run(args.journal, env, rows)
            print("run #" + str(run_id) + " saved to " + args.journal)
        except PermissionError:
            base, ext = os.path.splitext(args.journal)
            alt = base + "_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ext
            import shutil
            shutil.copyfile(args.journal, alt)
            run_id = append_run(alt, env, rows)
            print("journal is open in Excel, run #" + str(run_id) + " saved to " + alt)
    bad = sum(1 for _, _, _, _, s in rows if s == "FAIL")
    return 1 if bad else 0
if __name__ == "__main__":
    sys.exit(main())

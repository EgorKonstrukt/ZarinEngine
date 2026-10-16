# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import ast
import importlib.machinery
import io
import os
import py_compile
import subprocess
import sys
import tokenize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTS = (".py",) + tuple(importlib.machinery.EXTENSION_SUFFIXES)
ALIAS = {"nodmod": "plugins/tracker_music_plugin/libs/nodmod"}
SKIP_TOPS = set(sys.stdlib_module_names) | {
    "numpy", "PySide6", "qtawesome", "moderngl", "msgpack", "PIL", "psutil",
    "OpenGL", "yaml", "aiohttp", "websockets", "mcp", "mcp_types", "pydantic",
    "tiktoken", "numba", "scipy", "matplotlib", "cv2", "imageio", "assimp",
    "pybullet", "culverin", "physx", "xr", "openal", "al", "winreg",
}
ALLOW_BIG = {
    "editor/panels/project/panel.py",
    "editor/panels/project/pane.py",
    "editor/panels/project/widgets.py",
    "editor/panels/project/fs_ops.py",
    "plugins/tracker_music_plugin/libs/nodmod/xmsong.py",
    "plugins/tracker_music_plugin/libs/nodmod/modsong.py",
    "plugins/tracker_music_plugin/libs/nodmod/song.py",
    "plugins/tracker_music_plugin/libs/nodmod/s3msong.py",
    "plugins/tracker_music_plugin/libs/nodmod/types.py",
}
ALLOW_UNDEF = {"__compiled__"}
ALLOW_UNREGISTERED = {"SkyIbl", "RaytraceComponent"}
KNOWN_SMOKE_FAILS = {"test_compression_async.py", "test_prop_picker.py"}
MAX_LINES = 450


def _files():
    out = []
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in (".venv", "__pycache__", "NodeGraphQt", ".git", "build", "dist", "linux", "~")]
        if "~" in dp.split(os.sep):
            continue
        for f in fn:
            if f.endswith(".py"):
                out.append(os.path.join(dp, f))
    return sorted(out)


def _rel(p):
    return os.path.relpath(p, ROOT).replace(os.sep, "/")


def _new_files():
    try:
        proc = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT, capture_output=True, text=True, timeout=120)
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    out = []
    for line in proc.stdout.splitlines():
        if line.startswith("??"):
            p = line[3:].strip().strip('"').replace("/", os.sep)
            if not p.endswith(".py"):
                continue
            rel = p.replace(os.sep, "/")
            if rel.startswith("tests/") or rel.startswith("~/") or "/~/" in rel or rel.startswith("."):
                continue
            out.append(os.path.join(ROOT, p))
    return sorted(out)


def check_compile(files):
    bad = []
    for p in files:
        try:
            py_compile.compile(p, doraise=True)
        except Exception as e:
            bad.append((_rel(p), str(e).splitlines()[0][:100] if str(e) else "compile error"))
    return bad


def check_comments(files):
    bad = []
    for p in files:
        try:
            with open(p, "rb") as f:
                toks = list(tokenize.tokenize(f.readline))
        except Exception:
            continue
        code_started = False
        for t in toks:
            if t.type in (tokenize.NEWLINE, tokenize.NL, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING):
                continue
            if t.type == tokenize.COMMENT:
                if code_started:
                    bad.append((_rel(p), t.start[0]))
                continue
            code_started = True
    return bad


def check_docstrings(files):
    bad = []
    for p in files:
        try:
            tree = ast.parse(io.open(p, encoding="utf-8", errors="ignore").read())
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                body = getattr(node, "body", [])
                if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                    bad.append((_rel(p), getattr(node, "lineno", 0)))
    return bad


def check_size(files):
    bad = []
    for p in files:
        try:
            with io.open(p, encoding="utf-8", errors="ignore") as f:
                n = sum(1 for _ in f)
        except Exception:
            continue
        if n > MAX_LINES and _rel(p) not in ALLOW_BIG:
            bad.append((_rel(p), n))
    return bad


BUILTINS = {"__name__", "__doc__", "__package__", "__loader__", "__spec__", "__file__", "__cached__", "__build_class__", "__compiled__", "__builtins__"}


def _defined_names(tree):
    out = set(dir(__builtins__)) | BUILTINS
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
            args = getattr(n, "args", None)
            if args is not None:
                for a in list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs):
                    out.add(a.arg)
                if args.vararg:
                    out.add(args.vararg.arg)
                if args.kwarg:
                    out.add(args.kwarg.arg)
        elif isinstance(n, ast.Lambda):
            for a in list(n.args.posonlyargs) + list(n.args.args) + list(n.args.kwonlyargs):
                out.add(a.arg)
            if n.args.vararg:
                out.add(n.args.vararg.arg)
            if n.args.kwarg:
                out.add(n.args.kwarg.arg)
        elif isinstance(n, ast.Import):
            for a in n.names:
                out.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, ast.ImportFrom):
            for a in (n.names or []):
                if a.name != "*":
                    out.add(a.asname or a.name)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            out.add(n.id)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            out.add(n.name)
    return out


class _Loads(ast.NodeVisitor):
    def __init__(self):
        self.out = []
        self.skip = 0
    def _ann(self, node):
        self.skip += 1
        self.visit(node)
        self.skip -= 1
    def visit_FunctionDef(self, node):
        for d in node.decorator_list:
            self.visit(d)
        for d in list(node.args.defaults) + [x for x in node.args.kw_defaults if x]:
            self.visit(d)
        for a in list(node.args.posonlyargs) + list(node.args.args) + list(node.args.kwonlyargs):
            if a.annotation:
                self._ann(a.annotation)
        if node.returns:
            self._ann(node.returns)
        for s in node.body:
            self.visit(s)
    visit_AsyncFunctionDef = visit_FunctionDef
    def visit_AnnAssign(self, node):
        if node.value:
            self.visit(node.value)
        self._ann(node.annotation)
        self.visit(node.target)
    def visit_ClassDef(self, node):
        for d in node.decorator_list:
            self.visit(d)
        for s in node.body:
            self.visit(s)
    def visit_If(self, node):
        if isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
            return
        self.generic_visit(node)
    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load) and not self.skip:
            self.out.append((node.lineno, node.id))


def check_undefined(files):
    bad = []
    for p in files:
        try:
            tree = ast.parse(io.open(p, encoding="utf-8", errors="ignore").read())
        except Exception:
            continue
        if any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "__getattr__" for n in ast.walk(tree)):
            continue
        defined = _defined_names(tree)
        v = _Loads()
        v.visit(tree)
        seen = set()
        for lineno, name in v.out:
            if name in defined or name in BUILTINS or (p, name) in seen:
                continue
            seen.add((p, name))
            bad.append((_rel(p), lineno, name))
    return bad


class _TrySkip(ast.NodeVisitor):
    def __init__(self):
        self.depth = 0
        self.found = []
    def visit_Try(self, node):
        self.depth += 1
        self.generic_visit(node)
        self.depth -= 1
    def visit_Import(self, node):
        if self.depth == 0:
            self.found.append([a.name for a in node.names])
    def visit_ImportFrom(self, node):
        if self.depth == 0 and (node.level or 0) == 0 and node.module:
            self.found.append([node.module])


def check_imports(files):
    bad = []
    for p in files:
        try:
            tree = ast.parse(io.open(p, encoding="utf-8", errors="ignore").read())
        except Exception:
            continue
        v = _TrySkip()
        v.visit(tree)
        for names in v.found:
            for dotted in names:
                top = dotted.split(".")[0]
                if top in SKIP_TOPS:
                    continue
                if top in ALIAS:
                    dotted = ALIAS[top] + dotted[len(top):]
                    top = dotted.split(".")[0]
                if top not in ("core", "editor", "plugins", "physics_solvers", "tools", "tests", "playerp", "nodmod", "main", "player"):
                    continue
                rel = os.path.join(ROOT, *dotted.split("."))
                if os.path.isdir(rel):
                    continue
                if not (os.path.isfile(rel + ".py") or os.path.isfile(os.path.join(rel, "__init__.py")) or any(os.path.isfile(rel + e) for e in EXTS[1:])):
                    bad.append((_rel(p), dotted))
    return sorted(set(bad))


def check_register():
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    try:
        import core.components as _c
        from core.ecs import Component, ComponentRegistry
    except Exception as e:
        return [("core.components import", str(e).splitlines()[0][:100] if str(e) else "import error")]
    seen = set()
    stack = list(Component.__subclasses__())
    subs = []
    while stack:
        c = stack.pop()
        if c in seen:
            continue
        seen.add(c)
        subs.append(c)
        stack.extend(c.__subclasses__())
    bad = []
    for c in subs:
        name = c.__name__
        if "Mixin" in name or "Base" in name or name.startswith("_"):
            continue
        try:
            reg = ComponentRegistry.get(name)
        except Exception:
            reg = None
        if reg is None and name not in ALLOW_UNREGISTERED:
            bad.append((c.__module__, name))
    return sorted(set(bad))


def run_smokes():
    env = dict(os.environ)
    env.setdefault("PYTHONPATH", ROOT)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    proc = subprocess.run([sys.executable, "tests/smoke/run_smokes.py"], cwd=ROOT, env=env, capture_output=True, text=True)
    fails = set()
    for line in (proc.stdout + proc.stderr).splitlines():
        if line.startswith("FAILED:"):
            fails = {x.strip() for x in line.split(":", 1)[1].split(",")}
    return sorted(fails)


def main():
    files = _files()
    scoped = _new_files()
    style_files = scoped if scoped else files
    fails = 0
    for title, items, fmt in (
        ("compile", check_compile(files), lambda x: f"{x[0]}: {x[1]}"),
        ("comments", check_comments(style_files), lambda x: f"{x[0]}:{x[1]}"),
        ("docstrings", check_docstrings(style_files), lambda x: f"{x[0]}:{x[1]}"),
        ("size>450", check_size(files), lambda x: f"{x[0]} ({x[1]} строк)"),
        ("undefined", check_undefined(files), lambda x: f"{x[0]}:{x[1]}: {x[2]}"),
        ("imports", check_imports(files), lambda x: f"{x[0]} -> {x[1]}"),
        ("register", check_register(), lambda x: f"{x[0]}.{x[1]}"),
    ):
        if items:
            fails += 1
            print(f"[{title}] {len(items)}:")
            for it in items[:25]:
                print(f"  {fmt(it)}")
    if "--smoke" in sys.argv:
        fails_smoke = run_smokes()
        extra = [f for f in fails_smoke if f not in KNOWN_SMOKE_FAILS]
        print(f"[smoke] failures: {fails_smoke or 'none'}")
        if extra:
            fails += 1
            print(f"[smoke] NEW failures vs baseline: {extra}")
    print("GATE " + ("FAIL" if fails else "OK"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

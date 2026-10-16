# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import subprocess
from PySide6.QtCore import QThread, Signal

def _open_url(url: str):
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass


def _find_git() -> str:
    for candidate in ["git.exe", "git"]:
        try:
            r = subprocess.run([candidate, "--version"], capture_output=True,
                               text=True, timeout=5)
            if r.returncode == 0:
                return candidate
        except FileNotFoundError:
            continue
    return ""


def _git_run(git: str, args: list[str], cwd: str | None = None,
             timeout: int = 30) -> tuple[int, str, str]:
    try:
        r = subprocess.run([git] + args, capture_output=True, text=True,
                           cwd=cwd, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError:
        return -2, "", "git not found"
    except Exception as e:
        return -3, "", str(e)


class _GitProcess(QThread):
    finished = Signal(int, str, str)

    def __init__(self, git: str, args: list[str], cwd: str | None = None):
        super().__init__()
        self._git = git
        self._args = args
        self._cwd = cwd

    def run(self):
        rc, out, err = _git_run(self._git, self._args, self._cwd, timeout=120)
        self.finished.emit(rc, out, err)


class _Git:
    def __init__(self):
        self._path = _find_git()
        self._repo_root: str = ""
        self._cwd: str = ""

    @property
    def available(self) -> bool:
        return bool(self._path)

    @property
    def repo_root(self) -> str:
        return self._repo_root

    def detect(self, path: str) -> bool:
        if not self._path:
            return False
        rc, out, _ = _git_run(self._path, ["rev-parse", "--show-toplevel"],
                               cwd=path)
        if rc == 0:
            self._repo_root = out.strip()
            self._cwd = self._repo_root
            return True
        self._repo_root = ""
        self._cwd = ""
        return False

    def run_sync(self, *args: str, timeout: int = 30) -> tuple[int, str, str]:
        return _git_run(self._path, list(args), self._cwd, timeout)

    def run_async(self, *args: str) -> _GitProcess:
        t = _GitProcess(self._path, list(args), self._cwd)
        t.start()
        return t

    def status(self) -> tuple[int, str, str]:
        return self.run_sync("status", "--porcelain", "-u")

    def branch_info(self) -> tuple[int, str, str]:
        return self.run_sync("rev-parse", "--abbrev-ref", "HEAD")

    def branch_list(self) -> tuple[int, str, str]:
        return self.run_sync("branch", "-a")

    def current_branch(self) -> str:
        rc, out, _ = self.branch_info()
        if rc == 0:
            return out.strip() or "HEAD"
        return ""

    def ahead_behind(self, branch: str = "") -> str:
        if not branch:
            branch = self.current_branch()
        if not branch:
            return ""
        upstream = f"{branch}@{{upstream}}"
        rc, out, _ = self.run_sync("rev-list", "--left-right",
                                    "--count", f"{upstream}...{branch}",
                                    timeout=10)
        if rc == 0:
            parts = out.strip().split()
            if len(parts) == 2:
                behind, ahead = parts[0], parts[1]
                if behind != "0" or ahead != "0":
                    return f" [+{ahead}/-{behind}]"
        return ""

    def staged_diff(self) -> str:
        rc, out, _ = self.run_sync("diff", "--cached", "--no-color", timeout=15)
        return out if rc == 0 else ""

    def unstaged_diff(self) -> str:
        rc, out, _ = self.run_sync("diff", "--no-color", timeout=15)
        return out if rc == 0 else ""

    def file_diff(self, path: str, staged: bool = False) -> str:
        args = ["diff", "--no-color"]
        if staged:
            args.append("--cached")
        args.append("--")
        args.append(path)
        rc, out, _ = self.run_sync(*args, timeout=15)
        return out if rc == 0 else ""

    def add(self, paths: list[str]) -> tuple[int, str, str]:
        return self.run_sync("add", "--", *paths)

    def unstage(self, paths: list[str]) -> tuple[int, str, str]:
        return self.run_sync("restore", "--staged", "--", *paths)

    def restore(self, paths: list[str]) -> tuple[int, str, str]:
        return self.run_sync("restore", "--", *paths)

    def commit(self, message: str, amend: bool = False,
               signoff: bool = False) -> tuple[int, str, str]:
        args = ["commit"]
        if amend:
            args.append("--amend")
        if signoff:
            args.append("--signoff")
        args.extend(["-m", message])
        return self.run_sync(*args)

    def log(self, count: int = 100) -> list[dict]:
        fmt = "%H%n%h%n%an%n%ae%n%at%n%s%n%P%n"
        rc, out, _ = self.run_sync("log", f"--max-count={count}",
                                    f"--format={fmt}", "--date=short",
                                    "--decorate=short", "--simplify-merges",
                                    timeout=15)
        if rc != 0:
            return []
        commits = []
        for block in out.strip().split("\n\n"):
            block = block.strip()
            if not block:
                continue
            lines = block.split("\n")
            if len(lines) < 6:
                continue
            c = {
                "hash": lines[0],
                "short": lines[1],
                "author": lines[2],
                "email": lines[3],
                "time": int(lines[4]) if lines[4].isdigit() else 0,
                "message": lines[5],
                "parents": lines[6].split() if len(lines) > 6 else [],
            }
            commits.append(c)
        return commits

    def log_graph(self, count: int = 100) -> str:
        rc, out, _ = self.run_sync("log", f"--max-count={count}",
                                    "--oneline", "--graph",
                                    "--decorate=short", "--all",
                                    timeout=15)
        return out if rc == 0 else ""

    def create_branch(self, name: str) -> tuple[int, str, str]:
        return self.run_sync("branch", name)

    def switch_branch(self, name: str) -> tuple[int, str, str]:
        return self.run_sync("checkout", name)

    def delete_branch(self, name: str, force: bool = False) -> tuple[int, str, str]:
        args = ["branch"]
        if force:
            args.append("-D")
        else:
            args.append("-d")
        args.append(name)
        return self.run_sync(*args)

    def merge_branch(self, name: str) -> tuple[int, str, str]:
        return self.run_sync("merge", name)

    def stash_list(self) -> list[dict]:
        rc, out, _ = self.run_sync("stash", "list",
                                    "--format=%gd%n%gs%n%at%n")
        if rc != 0 or not out.strip():
            return []
        stashes = []
        for block in out.strip().split("\n\n"):
            block = block.strip()
            if not block:
                continue
            lines = block.split("\n")
            if len(lines) < 2:
                continue
            s = {
                "ref": lines[0],
                "message": lines[1],
                "time": int(lines[2]) if len(lines) > 2 and lines[2].isdigit() else 0,
            }
            stashes.append(s)
        return stashes

    def stash_push(self, message: str = "") -> tuple[int, str, str]:
        args = ["stash", "push"]
        if message:
            args.extend(["-m", message])
        return self.run_sync(*args)

    def stash_pop(self, ref: str = "stash@{0}") -> tuple[int, str, str]:
        return self.run_sync("stash", "pop", ref)

    def stash_drop(self, ref: str = "stash@{0}") -> tuple[int, str, str]:
        return self.run_sync("stash", "drop", ref)

    def remotes(self) -> list[dict]:
        rc, out, _ = self.run_sync("remote", "-v")
        if rc != 0:
            return []
        seen = set()
        result = []
        for line in out.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 2:
                name = parts[0]
                url = parts[1]
                if name not in seen:
                    seen.add(name)
                    result.append({"name": name, "url": url})
        return result

    def push(self, remote: str = "origin",
             branch: str = "") -> _GitProcess:
        args = ["push"]
        if remote:
            args.append(remote)
        if branch:
            args.append(branch)
        return self.run_async(*args)

    def pull(self, remote: str = "origin",
             branch: str = "") -> _GitProcess:
        args = ["pull"]
        if remote:
            args.append(remote)
        if branch:
            args.append(branch)
        return self.run_async(*args)

    def fetch(self, remote: str = "") -> _GitProcess:
        args = ["fetch"]
        if remote:
            args.append(remote)
        return self.run_async(*args)

    def tags(self) -> list[str]:
        rc, out, _ = self.run_sync("tag", "-l", timeout=10)
        if rc != 0:
            return []
        return [t for t in out.strip().split("\n") if t]

    def blame(self, path: str) -> str:
        rc, out, _ = self.run_sync("blame", "--date=short", "--", path,
                                    timeout=15)
        return out if rc == 0 else ""

    def show_commit(self, rev: str) -> str:
        rc, out, _ = self.run_sync("show", "--no-color", "--stat", rev,
                                    timeout=15)
        return out if rc == 0 else ""


_parse_cache: dict[str, list[dict]] = {}


def _parse_porcelain(status_output: str) -> list[dict]:
    if status_output in _parse_cache:
        return _parse_cache[status_output]
    entries: list[dict] = []
    for line in status_output.strip().split("\n"):
        line = line.rstrip()
        if not line or len(line) < 3:
            continue
        xy = line[:2]
        path = line[3:]
        if xy[1] == " ":
            staged = xy[0] != " "
        else:
            staged = xy[0] != " "
        unstaged = xy[1] != " "
        if xy[0] == "?" and xy[1] == "?":
            staged = False
            unstaged = False
            status = "untracked"
        elif xy[0] == "!" and xy[1] == "!":
            continue
        elif xy[0] == "U" or xy[1] == "U":
            status = "conflict"
        elif staged and unstaged:
            status = "modified"
        elif staged:
            status = "staged"
        elif unstaged:
            status = "unstaged"
        else:
            status = "unknown"
        entries.append({
            "path": path,
            "status": status,
            "xy": xy,
            "staged": staged,
            "unstaged": unstaged,
        })
    _parse_cache[status_output] = entries
    return entries

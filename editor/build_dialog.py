from __future__ import annotations
import sys
import os
import json
import subprocess
import threading
import shutil
from pathlib import Path
from typing import Optional
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QPushButton, QLabel, QLineEdit, QCheckBox,
                             QGroupBox, QTextEdit, QProgressBar, QFileDialog,
                             QMessageBox, QComboBox, QSpinBox,
                             QTabWidget, QWidget)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor


ROOT = Path(__file__).resolve().parent.parent
_BUILD_PROFILES_PATH = ROOT / "build_profiles.json"

if sys.platform == "win32":
    _ASSIMP_LIB_NAME = "assimp-vc143-mt.dll"
else:
    _ASSIMP_LIB_NAME = "libassimp.so.6.0.5"


class Profile:
    def __init__(self, name: str = "Default"):
        self.name = name
        self.target: str = "editor"
        self.backend: str = "nuitka"
        self.output_dir: str = str(ROOT / "build_output")
        self.console: bool = True
        self.onefile: bool = False
        self.include_packages: list[str] = ["core", "editor", "plugins", "physics_solvers"]
        self.include_dirs: dict[str, str] = {
            "assets": "assets",
            "scenes": "scenes",
            "materials": "materials",
            "prefabs": "prefabs",
            "editor/shaders": "editor/shaders",
        }
        self.include_files: list[tuple[str, str]] = [
            (_ASSIMP_LIB_NAME, _ASSIMP_LIB_NAME),
            ("1.mat", "1.mat"),
        ]
        self.extra_args: str = ""

        self.nuitka_enable_pyqt6: bool = True
        self.nuitka_enable_numpy: bool = True
        self.nuitka_follow_imports: bool = True
        self.nuitka_remove_output: bool = True
        self.nuitka_jobs: int = 0
        self.nuitka_nofollow_imports: list[str] = [
            "PIL", "matplotlib", "cv2", "scipy", "IPython", "notebook",
            "tensorflow", "torch", "transformers", "pydoc", "tests", "test",
        ]

        self.pyinstaller_hidden_imports: list[str] = [
            "core", "editor", "plugins", "physics_solvers",
            "PyQt6", "moderngl", "numpy", "numba", "pyopenal",
            "pybullet",
        ]
        self.pyinstaller_upx: bool = False
        self.pyinstaller_debug: bool = False
        self.pyinstaller_clean: bool = True

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "target": self.target,
            "backend": self.backend,
            "output_dir": self.output_dir,
            "console": self.console,
            "onefile": self.onefile,
            "include_packages": list(self.include_packages),
            "include_dirs": dict(self.include_dirs),
            "include_files": [list(x) for x in self.include_files],
            "extra_args": self.extra_args,
            "nuitka_enable_pyqt6": self.nuitka_enable_pyqt6,
            "nuitka_enable_numpy": self.nuitka_enable_numpy,
            "nuitka_follow_imports": self.nuitka_follow_imports,
            "nuitka_remove_output": self.nuitka_remove_output,
            "nuitka_jobs": self.nuitka_jobs,
            "nuitka_nofollow_imports": list(self.nuitka_nofollow_imports),
            "pyinstaller_hidden_imports": list(self.pyinstaller_hidden_imports),
            "pyinstaller_upx": self.pyinstaller_upx,
            "pyinstaller_debug": self.pyinstaller_debug,
            "pyinstaller_clean": self.pyinstaller_clean,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Profile:
        p = cls(d.get("name", "Default"))
        p.target = d.get("target", p.target)
        p.backend = d.get("backend", p.backend)
        p.output_dir = d.get("output_dir", p.output_dir)
        p.console = d.get("console", p.console)
        p.onefile = d.get("onefile", p.onefile)
        p.include_packages = list(d.get("include_packages", p.include_packages))
        p.include_dirs = dict(d.get("include_dirs", p.include_dirs))
        p.include_files = [tuple(x) for x in d.get("include_files", [list(x) for x in p.include_files])]
        p.extra_args = d.get("extra_args", p.extra_args)
        p.nuitka_enable_pyqt6 = d.get("nuitka_enable_pyqt6", p.nuitka_enable_pyqt6)
        p.nuitka_enable_numpy = d.get("nuitka_enable_numpy", p.nuitka_enable_numpy)
        p.nuitka_follow_imports = d.get("nuitka_follow_imports", p.nuitka_follow_imports)
        p.nuitka_remove_output = d.get("nuitka_remove_output", p.nuitka_remove_output)
        p.nuitka_jobs = d.get("nuitka_jobs", p.nuitka_jobs)
        p.nuitka_nofollow_imports = list(d.get("nuitka_nofollow_imports", p.nuitka_nofollow_imports))
        p.pyinstaller_hidden_imports = list(d.get("pyinstaller_hidden_imports", p.pyinstaller_hidden_imports))
        p.pyinstaller_upx = d.get("pyinstaller_upx", p.pyinstaller_upx)
        p.pyinstaller_debug = d.get("pyinstaller_debug", p.pyinstaller_debug)
        p.pyinstaller_clean = d.get("pyinstaller_clean", p.pyinstaller_clean)
        return p

    def build_args(self) -> list[str]:
        if self.backend == "pyinstaller":
            return self._pyinstaller_args()
        return self._nuitka_args()

    @property
    def _entry_point(self) -> Path:
        return ROOT / "player.py" if self.target == "player" else ROOT / "main.py"

    def _nuitka_args(self) -> list[str]:
        py_exe = sys.executable
        args = [py_exe, "-m", "nuitka", "--standalone"]
        args.append(f"--output-dir={self.output_dir}")
        if self.onefile:
            args.append("--onefile")
        if self.nuitka_enable_pyqt6:
            args.append("--enable-plugin=pyqt6")
        if self.nuitka_enable_numpy:
            args.append("--enable-plugin=numpy")
        if not self.nuitka_follow_imports:
            args.append("--nofollow-imports")
        if self.nuitka_remove_output:
            args.append("--remove-output")
        if self.nuitka_jobs > 0:
            args.append(f"--jobs={self.nuitka_jobs}")
        if not self.console:
            args.append("--disable-console")
        if self.extra_args:
            args.extend(self.extra_args.split())
        for pkg in self.include_packages:
            pkg = pkg.strip()
            if pkg:
                args.append(f"--include-package={pkg}")
        for src, dst in self.include_dirs.items():
            src = src.strip()
            dst = dst.strip()
            if src and dst:
                full_src = ROOT / src
                if full_src.exists():
                    args.append(f"--include-data-dir={full_src}={dst}")
        for src, dst in self.include_files:
            src = src.strip()
            dst = dst.strip()
            if src and dst:
                full_src = ROOT / src
                if full_src.exists():
                    args.append(f"--include-data-file={full_src}={dst}")
        for mod in self.nuitka_nofollow_imports:
            mod = mod.strip()
            if mod:
                args.append(f"--nofollow-import-to={mod}")
        args.append("--warn-unusual-code")
        args.append(str(self._entry_point))
        return args

    def _pyinstaller_args(self) -> list[str]:
        py_exe = sys.executable
        args = [py_exe, "-m", "PyInstaller"]
        if self.onefile:
            args.append("--onefile")
        else:
            args.append("--onedir")
        if not self.console:
            args.append("--noconsole")
        if self.pyinstaller_clean:
            args.append("--clean")
        if self.pyinstaller_debug:
            args.append("--debug")
        if self.pyinstaller_upx:
            args.append("--upx-dir=")
        args.append(f"--distpath={self.output_dir}")
        args.append(f"--specpath={self.output_dir}")
        args.append(f"--workpath={self.output_dir}/__pycache__")
        name = "Zarin Engine" if self.target == "editor" else "Zarin Player"
        args.append(f"--name={name}")
        for pkg in self.include_packages:
            pkg = pkg.strip()
            if pkg:
                args.append(f"--hidden-import={pkg}")
        for mod in self.pyinstaller_hidden_imports:
            mod = mod.strip()
            if mod:
                args.append(f"--hidden-import={mod}")
        for src, dst in self.include_dirs.items():
            src = src.strip()
            dst = dst.strip()
            if src and dst:
                full_src = ROOT / src
                if full_src.exists():
                    args.append(f"--add-data={full_src}{os.pathsep}{dst}")
        for src, dst in self.include_files:
            src = src.strip()
            dst = dst.strip()
            if src and dst:
                full_src = ROOT / src
                if full_src.exists():
                    args.append(f"--add-data={full_src}{os.pathsep}{dst}")
        if self.extra_args:
            args.extend(self.extra_args.split())
        args.append(str(self._entry_point))
        return args


def load_profiles() -> dict[str, Profile]:
    if _BUILD_PROFILES_PATH.exists():
        try:
            with open(_BUILD_PROFILES_PATH, "r") as f:
                data = json.load(f)
            profiles = {}
            for item in data:
                p = Profile.from_dict(item)
                profiles[p.name] = p
            if profiles:
                return profiles
        except Exception:
            pass
    return {"Default": Profile("Default")}


def save_profiles(profiles: dict[str, Profile]):
    data = [p.to_dict() for p in profiles.values()]
    try:
        with open(_BUILD_PROFILES_PATH, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Failed to save profiles: {e}")


class BuildDialog(QDialog):
    _log_signal = pyqtSignal(str)
    _done_signal = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._profiles = load_profiles()
        self._current_profile: Optional[Profile] = None
        self._build_process: Optional[subprocess.Popen] = None
        self._build_thread: Optional[threading.Thread] = None
        self._cancelled = False

        self.setWindowTitle("Build Zarin Engine")
        self.setMinimumSize(800, 600)
        self.resize(900, 700)

        self._setup_ui()
        self._connect_signals()

        self._log_signal.connect(self._append_log)
        self._done_signal.connect(self._on_build_done)
        self._load_profile("Default")

    def _setup_ui(self):
        main = QVBoxLayout(self)
        main.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Profile:"))
        self._profile_combo = QComboBox()
        self._profile_combo.setMinimumWidth(180)
        toolbar.addWidget(self._profile_combo)

        self._save_btn = QPushButton("Save")
        self._save_btn.setFixedWidth(60)
        toolbar.addWidget(self._save_btn)

        self._save_as_btn = QPushButton("Save As...")
        self._save_as_btn.setFixedWidth(80)
        toolbar.addWidget(self._save_as_btn)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setFixedWidth(60)
        toolbar.addWidget(self._delete_btn)

        toolbar.addStretch()
        toolbar.addWidget(QLabel("Backend:"))
        self._backend_combo = QComboBox()
        self._backend_combo.addItem("Nuitka", "nuitka")
        self._backend_combo.addItem("PyInstaller", "pyinstaller")
        self._backend_combo.setFixedWidth(120)
        toolbar.addWidget(self._backend_combo)

        main.addLayout(toolbar)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_general_tab(), "General")
        self._tabs.addTab(self._build_packages_tab(), "Packages & Assets")
        self._tabs.addTab(self._build_advanced_tab(), "Advanced")
        main.addWidget(self._tabs, 1)

        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout(output_group)
        output_layout.setContentsMargins(4, 4, 4, 4)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)
        self._progress_bar.hide()
        output_layout.addWidget(self._progress_bar)

        self._log_output = QTextEdit()
        self._log_output.setReadOnly(True)
        self._log_output.setFont(QFont("Consolas", 9))
        self._log_output.setMinimumHeight(120)
        output_layout.addWidget(self._log_output)

        btn_layout = QHBoxLayout()
        self._build_btn = QPushButton("Build")
        self._build_btn.setMinimumHeight(32)
        self._build_btn.setStyleSheet("QPushButton { font-weight: bold; padding: 4px 20px; }")
        btn_layout.addStretch()
        btn_layout.addWidget(self._build_btn)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setMinimumHeight(32)
        self._cancel_btn.setEnabled(False)
        btn_layout.addWidget(self._cancel_btn)

        self._open_output_btn = QPushButton("Open Output Folder")
        self._open_output_btn.setEnabled(False)
        btn_layout.addWidget(self._open_output_btn)

        close_btn = QPushButton("Close")
        close_btn.setMinimumHeight(32)
        btn_layout.addWidget(close_btn)
        output_layout.addLayout(btn_layout)

        main.addWidget(output_group)

        close_btn.clicked.connect(self.close)
        self._build_btn.clicked.connect(self._start_build)
        self._cancel_btn.clicked.connect(self._cancel_build)
        self._open_output_btn.clicked.connect(self._open_output_folder)
        self._save_btn.clicked.connect(self._save_current_profile)
        self._save_as_btn.clicked.connect(self._save_as_profile)
        self._delete_btn.clicked.connect(self._delete_profile)

    def _make_group(self, title: str, parent) -> QGroupBox:
        g = QGroupBox(title, parent)
        g.setLayout(QVBoxLayout())
        g.layout().setContentsMargins(8, 8, 8, 8)
        g.layout().setSpacing(4)
        return g

    def _build_general_tab(self) -> QWidget:
        w = QWidget()
        layout = QFormLayout(w)
        layout.setContentsMargins(12, 12, 12, 12)

        self._target_combo = QComboBox()
        self._target_combo.addItem("Editor (main.py)", "editor")
        self._target_combo.addItem("Player (player.py)", "player")
        layout.addRow("Target:", self._target_combo)

        self._output_dir_edit = QLineEdit()
        self._output_dir_edit.setPlaceholderText("Output directory...")
        browse_btn = QPushButton("...")
        browse_btn.setFixedWidth(32)
        browse_btn.clicked.connect(self._browse_output_dir)
        h = QHBoxLayout()
        h.addWidget(self._output_dir_edit, 1)
        h.addWidget(browse_btn)
        layout.addRow("Output Dir:", h)

        self._onefile_cb = QCheckBox("Single file (onefile / --onefile)")
        layout.addRow("Mode:", self._onefile_cb)

        self._console_cb = QCheckBox("Show console window")
        self._console_cb.setChecked(True)
        layout.addRow("Console:", self._console_cb)

        layout.addRow("", QLabel(""))

        self._nuitka_jobs_label = QLabel("Parallel jobs:")
        self._nuitka_jobs_spin = QSpinBox()
        self._nuitka_jobs_spin.setRange(0, 64)
        self._nuitka_jobs_spin.setSpecialValueText("Auto")
        self._nuitka_jobs_spin.setValue(0)
        layout.addRow(self._nuitka_jobs_label, self._nuitka_jobs_spin)

        self._backend_note = QLabel()
        self._backend_note.setStyleSheet("color: #888; font-style: italic;")
        layout.addRow(self._backend_note)

        return w

    def _build_packages_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 12, 12, 12)

        pkg_group = self._make_group("Include Packages (one per line)", w)
        self._packages_edit = QTextEdit()
        self._packages_edit.setMaximumHeight(100)
        self._packages_edit.setPlaceholderText("core\neditor\nplugins\nphysics_solvers")
        pkg_group.layout().addWidget(self._packages_edit)
        layout.addWidget(pkg_group)

        dirs_group = self._make_group("Include Data Directories (source = target)", w)
        self._dirs_edit = QTextEdit()
        self._dirs_edit.setMaximumHeight(120)
        self._dirs_edit.setPlaceholderText("assets = assets\nscenes = scenes\nmaterials = materials\n...")
        dirs_group.layout().addWidget(self._dirs_edit)
        layout.addWidget(dirs_group)

        files_group = self._make_group("Include Data Files (source = target)", w)
        self._files_edit = QTextEdit()
        self._files_edit.setMaximumHeight(100)
        self._files_edit.setPlaceholderText(f"{_ASSIMP_LIB_NAME} = {_ASSIMP_LIB_NAME}")
        files_group.layout().addWidget(self._files_edit)
        layout.addWidget(files_group)

        return w

    def _build_advanced_tab(self) -> QWidget:
        w = QWidget()
        scroll = QVBoxLayout(w)
        scroll.setContentsMargins(12, 12, 12, 12)

        self._nuitka_group = self._make_group("Nuitka Options", w)
        self._nuitka_pyqt6_cb = QCheckBox("Enable PyQt6 plugin")
        self._nuitka_pyqt6_cb.setChecked(True)
        self._nuitka_group.layout().addWidget(self._nuitka_pyqt6_cb)
        self._nuitka_numpy_cb = QCheckBox("Enable NumPy plugin")
        self._nuitka_numpy_cb.setChecked(True)
        self._nuitka_group.layout().addWidget(self._nuitka_numpy_cb)
        self._nuitka_follow_cb = QCheckBox("Follow all imports (may increase size)")
        self._nuitka_follow_cb.setChecked(True)
        self._nuitka_group.layout().addWidget(self._nuitka_follow_cb)
        self._nuitka_remove_cb = QCheckBox("Remove temporary build files")
        self._nuitka_remove_cb.setChecked(True)
        self._nuitka_group.layout().addWidget(self._nuitka_remove_cb)
        scroll.addWidget(self._nuitka_group)

        nofollow_group = self._make_group("Skip these modules (Nuitka, one per line)", w)
        self._nuitka_nofollow_edit = QTextEdit()
        self._nuitka_nofollow_edit.setMaximumHeight(120)
        self._nuitka_nofollow_edit.setPlaceholderText("PIL\nmatplotlib\ncv2\nscipy\ntorch\ntensorflow\n...")
        nofollow_group.layout().addWidget(self._nuitka_nofollow_edit)
        scroll.addWidget(nofollow_group)

        self._pyi_group = self._make_group("PyInstaller Options", w)
        self._pyi_upx_cb = QCheckBox("Enable UPX compression (if upx.exe is in PATH)")
        self._pyi_group.layout().addWidget(self._pyi_upx_cb)
        self._pyi_debug_cb = QCheckBox("Debug mode (--debug)")
        self._pyi_group.layout().addWidget(self._pyi_debug_cb)
        self._pyi_clean_cb = QCheckBox("Clean cache before build (--clean)")
        self._pyi_clean_cb.setChecked(True)
        self._pyi_group.layout().addWidget(self._pyi_clean_cb)
        scroll.addWidget(self._pyi_group)

        hi_group = self._make_group("Hidden imports (PyInstaller, one per line)", w)
        self._pyi_hidden_edit = QTextEdit()
        self._pyi_hidden_edit.setMaximumHeight(120)
        self._pyi_hidden_edit.setPlaceholderText("core\neditor\nPyQt6\nmoderngl\nnumpy\n...")
        hi_group.layout().addWidget(self._pyi_hidden_edit)
        scroll.addWidget(hi_group)

        extra_group = self._make_group("Extra arguments (both backends)", w)
        self._extra_edit = QLineEdit()
        self._extra_edit.setPlaceholderText("--lto=yes --no-deployment-flag=self-execution")
        extra_group.layout().addWidget(self._extra_edit)
        scroll.addWidget(extra_group)

        scroll.addStretch()
        return w

    def _connect_signals(self):
        self._profile_combo.currentTextChanged.connect(self._on_profile_changed)
        self._backend_combo.currentIndexChanged.connect(self._on_backend_changed)

    def _on_backend_changed(self):
        self._update_backend_visibility()

    def _update_backend_visibility(self):
        is_nuitka = self._backend_combo.currentData() == "nuitka"
        self._nuitka_group.setVisible(is_nuitka)
        self._nuitka_nofollow_edit.setVisible(is_nuitka)
        self._nuitka_jobs_label.setVisible(is_nuitka)
        self._nuitka_jobs_spin.setVisible(is_nuitka)
        self._pyi_group.setVisible(not is_nuitka)
        self._pyi_hidden_edit.setVisible(not is_nuitka)
        label = "Nuitka: compiling Python to C, slower build, faster runtime" if is_nuitka else "PyInstaller: bundles Python + interpreter, faster build, larger size"
        self._backend_note.setText(label)

    def _load_profile(self, name: str):
        if name in self._profiles:
            self._current_profile = self._profiles[name]
            self._apply_profile_to_ui()

    def _apply_profile_to_ui(self):
        p = self._current_profile
        if not p:
            return
        t_idx = self._target_combo.findData(p.target)
        if t_idx >= 0:
            self._target_combo.setCurrentIndex(t_idx)
        b_idx = self._backend_combo.findData(p.backend)
        if b_idx >= 0:
            self._backend_combo.setCurrentIndex(b_idx)
        self._output_dir_edit.setText(p.output_dir)
        self._onefile_cb.setChecked(p.onefile)
        self._console_cb.setChecked(p.console)
        self._nuitka_pyqt6_cb.setChecked(p.nuitka_enable_pyqt6)
        self._nuitka_numpy_cb.setChecked(p.nuitka_enable_numpy)
        self._nuitka_follow_cb.setChecked(p.nuitka_follow_imports)
        self._nuitka_remove_cb.setChecked(p.nuitka_remove_output)
        self._nuitka_jobs_spin.setValue(p.nuitka_jobs)
        self._extra_edit.setText(p.extra_args)
        self._packages_edit.setText("\n".join(p.include_packages))
        self._dirs_edit.setText("\n".join(f"{k} = {v}" for k, v in p.include_dirs.items()))
        self._files_edit.setText("\n".join(f"{k} = {v}" for k, v in p.include_files))
        self._nuitka_nofollow_edit.setText("\n".join(p.nuitka_nofollow_imports))
        self._pyi_hidden_edit.setText("\n".join(p.pyinstaller_hidden_imports))
        self._pyi_upx_cb.setChecked(p.pyinstaller_upx)
        self._pyi_debug_cb.setChecked(p.pyinstaller_debug)
        self._pyi_clean_cb.setChecked(p.pyinstaller_clean)
        self._update_backend_visibility()

    def _read_profile_from_ui(self) -> Profile:
        p = Profile()
        p.target = self._target_combo.currentData()
        p.backend = self._backend_combo.currentData()
        p.output_dir = self._output_dir_edit.text().strip()
        p.onefile = self._onefile_cb.isChecked()
        p.console = self._console_cb.isChecked()
        p.nuitka_enable_pyqt6 = self._nuitka_pyqt6_cb.isChecked()
        p.nuitka_enable_numpy = self._nuitka_numpy_cb.isChecked()
        p.nuitka_follow_imports = self._nuitka_follow_cb.isChecked()
        p.nuitka_remove_output = self._nuitka_remove_cb.isChecked()
        p.nuitka_jobs = self._nuitka_jobs_spin.value()
        p.extra_args = self._extra_edit.text().strip()
        p.include_packages = [
            x.strip() for x in self._packages_edit.toPlainText().split("\n") if x.strip()
        ]
        p.include_dirs = {}
        for line in self._dirs_edit.toPlainText().split("\n"):
            if "=" in line:
                k, v = line.split("=", 1)
                p.include_dirs[k.strip()] = v.strip()
        p.include_files = []
        for line in self._files_edit.toPlainText().split("\n"):
            if "=" in line:
                k, v = line.split("=", 1)
                p.include_files.append((k.strip(), v.strip()))
        p.nuitka_nofollow_imports = [
            x.strip() for x in self._nuitka_nofollow_edit.toPlainText().split("\n") if x.strip()
        ]
        p.pyinstaller_hidden_imports = [
            x.strip() for x in self._pyi_hidden_edit.toPlainText().split("\n") if x.strip()
        ]
        p.pyinstaller_upx = self._pyi_upx_cb.isChecked()
        p.pyinstaller_debug = self._pyi_debug_cb.isChecked()
        p.pyinstaller_clean = self._pyi_clean_cb.isChecked()
        return p

    def _on_profile_changed(self, name: str):
        if name in self._profiles:
            self._current_profile = self._profiles[name]
            self._apply_profile_to_ui()

    def _save_current_profile(self):
        if not self._current_profile:
            return
        p = self._read_profile_from_ui()
        p.name = self._current_profile.name
        self._profiles[p.name] = p
        self._current_profile = p
        save_profiles(self._profiles)

    def _save_as_profile(self):
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Save Profile As", "Profile name:")
        if ok and name:
            p = self._read_profile_from_ui()
            p.name = name
            self._profiles[name] = p
            save_profiles(self._profiles)
            self._refresh_profile_list()
            self._profile_combo.setCurrentText(name)

    def _delete_profile(self):
        name = self._profile_combo.currentText()
        if name == "Default":
            QMessageBox.warning(self, "Delete Profile", "Cannot delete the Default profile.")
            return
        reply = QMessageBox.question(self, "Delete Profile",
                                     f"Delete profile '{name}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self._profiles.pop(name, None)
            save_profiles(self._profiles)
            self._refresh_profile_list()

    def _refresh_profile_list(self):
        current = self._profile_combo.currentText()
        self._profile_combo.blockSignals(True)
        self._profile_combo.clear()
        for name in self._profiles:
            self._profile_combo.addItem(name)
        idx = self._profile_combo.findText(current)
        if idx >= 0:
            self._profile_combo.setCurrentIndex(idx)
        elif self._profile_combo.count() > 0:
            self._profile_combo.setCurrentIndex(0)
        self._profile_combo.blockSignals(False)

    def _browse_output_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if path:
            self._output_dir_edit.setText(path)

    def _append_log(self, text: str):
        self._log_output.moveCursor(QTextCursor.MoveOperation.End)
        self._log_output.insertPlainText(text)
        self._log_output.moveCursor(QTextCursor.MoveOperation.End)

    def _start_build(self):
        p = self._read_profile_from_ui()
        args = p.build_args()

        self._log_output.clear()
        self._build_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._open_output_btn.setEnabled(False)
        self._progress_bar.show()
        self._cancelled = False

        self._append_log(f">>> {' '.join(args)}\n\n")

        self._build_thread = threading.Thread(
            target=self._run_build,
            args=(args,),
            daemon=True,
        )
        self._build_thread.start()

    def _run_build(self, args: list[str]):
        try:
            startupinfo = None
            creationflags = 0
            if sys.platform == "win32":
                creationflags = subprocess.CREATE_NO_WINDOW

            self._build_process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=str(ROOT),
                creationflags=creationflags,
            )
            for line in self._build_process.stdout:
                if self._cancelled:
                    self._build_process.terminate()
                    break
                self._log_signal.emit(line)
            returncode = self._build_process.wait()
        except Exception as e:
            self._log_signal.emit(f"\nError: {e}\n")
            returncode = -1
        finally:
            self._build_process = None
            self._done_signal.emit(returncode)

    def _on_build_done(self, returncode: int):
        self._build_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._progress_bar.hide()

        if self._cancelled:
            self._append_log("\n=== BUILD CANCELLED ===\n")
            return

        if returncode == 0:
            self._append_log("\n=== BUILD SUCCEEDED ===\n")
            self._open_output_btn.setEnabled(True)

            p = self._read_profile_from_ui()
            out_dir = p.output_dir
            is_player = p.target == "player"
            nuitka_name = "player" if is_player else "main"
            pyi_name = "Zarin Player" if is_player else "Zarin Engine"
            nuitka_dist = Path(out_dir) / f"{nuitka_name}.dist"
            pyi_dist = Path(out_dir) / pyi_name
            exe_name = f"{nuitka_name}.exe"
            if nuitka_dist.exists():
                self._append_log(f"\nExecutable: {nuitka_dist / exe_name}\n")
            elif pyi_dist.exists():
                self._append_log(f"\nExecutable: {pyi_dist / f'{pyi_name}.exe'}\n")
        else:
            self._append_log(f"\n=== BUILD FAILED (code {returncode}) ===\n")
            QMessageBox.warning(self, "Build Failed",
                                f"Build exited with code {returncode}.\nCheck the log for details.")

    def _cancel_build(self):
        if self._build_process:
            self._cancelled = True
            self._build_process.terminate()
            self._append_log("\nCancelling...\n")
        self._cancel_btn.setEnabled(False)

    def _open_output_folder(self):
        p = self._read_profile_from_ui()
        is_player = p.target == "player"
        nuitka_name = "player" if is_player else "main"
        pyi_name = "Zarin Player" if is_player else "Zarin Engine"
        candidates = [
            Path(p.output_dir) / f"{nuitka_name}.dist",
            Path(p.output_dir) / pyi_name,
            Path(p.output_dir),
        ]
        for c in candidates:
            if c.exists():
                os.startfile(str(c))
                return

    def closeEvent(self, event):
        if self._build_process:
            reply = QMessageBox.question(self, "Build in Progress",
                                         "A build is running. Cancel and exit?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self._cancelled = True
                self._build_process.terminate()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def show_build_dialog(parent=None):
    dialog = BuildDialog(parent)
    dialog.exec()


if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    app.setApplicationName("Zarin Engine Builder")
    app.setStyle("Fusion")
    dialog = BuildDialog()
    dialog.show()
    sys.exit(app.exec())

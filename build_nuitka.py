import subprocess
import sys
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "build_output"

if sys.platform == "win32":
    _ASSIMP_SRC = "assimp-vc143-mt.dll"
else:
    _ASSIMP_SRC = "libassimp.so.6.0.5"

NUITKA_OPTIONS = [
    sys.executable, "-m", "nuitka",
    "--standalone",
    "--output-dir=" + str(OUTPUT_DIR),
    "--enable-plugin=pyqt6",
    "--include-package=core",
    "--include-package=editor",
    "--include-package=plugins",
    "--include-package=physics_solvers",
    "--include-data-dir=" + str(ROOT / "assets") + "=assets",
    "--include-data-dir=" + str(ROOT / "scenes") + "=scenes",
    "--include-data-dir=" + str(ROOT / "materials") + "=materials",
    "--include-data-dir=" + str(ROOT / "prefabs") + "=prefabs",
    "--include-data-dir=" + str(ROOT / "editor" / "shaders") + "=editor/shaders",
    "--include-data-file=" + str(ROOT / _ASSIMP_SRC) + "=" + _ASSIMP_SRC,
    "--include-data-file=" + str(ROOT / "1.mat") + "=1.mat",
    "--nofollow-import-to=PIL",
    "--nofollow-import-to=matplotlib",
    "--nofollow-import-to=cv2",
    "--nofollow-import-to=scipy",
    "--nofollow-import-to=IPython",
    "--nofollow-import-to=notebook",
    "--nofollow-import-to=tensorflow",
    "--nofollow-import-to=torch",
    "--nofollow-import-to=transformers",
    "--nofollow-import-to=pydoc",
    "--nofollow-import-to=tests",
    "--nofollow-import-to=test",
    "--remove-output",
    "--warn-unusual-code",
    str(ROOT / "main.py"),
]


def build():
    print("=== Zarin Engine Nuitka Build ===")
    print(f"Python: {sys.executable}")
    print(f"Root: {ROOT}")
    print()

    if OUTPUT_DIR.exists():
        print(f"Cleaning old output: {OUTPUT_DIR}")
        shutil.rmtree(OUTPUT_DIR)

    print("Running Nuitka...")
    print(" ".join(NUITKA_OPTIONS))
    print()

    result = subprocess.run(NUITKA_OPTIONS, cwd=str(ROOT))

    if result.returncode != 0:
        print(f"\nBuild failed with code {result.returncode}")
        sys.exit(result.returncode)

    print("\nBuild succeeded!")
    print(f"Output directory: {OUTPUT_DIR}")


if __name__ == "__main__":
    build()

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import argparse
import fnmatch
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.zplug.cli import _main_manage
from tools.zplug.cli import _receipts_dir
from tools.zplug.cli import _venv_site_packages
from tools.zplug.cli import install_pack
from tools.zplug.cli import list_installed_packs
from tools.zplug.cli import main
from tools.zplug.cli import uninstall_pack
from tools.zplug.pack import _bundle_into_stage
from tools.zplug.pack import _compile_tree_cython
from tools.zplug.pack import _compile_tree_nuitka
from tools.zplug.pack import _env_with_mingw
from tools.zplug.pack import _iter_package_modules
from tools.zplug.pack import _nuitka_flags
from tools.zplug.pack import _zpl_build_env
from tools.zplug.pack import build_zplugin
from tools.zplug.pack import create_library_pack
from tools.zplug.pack import download_wheels
from tools.zplug.pack import vendor_wheels
from tools.zplug.verify import _copy_dist_info
from tools.zplug.verify import _dist_top_levels
from tools.zplug.verify import _dist_version
from tools.zplug.verify import _ed_gen
from tools.zplug.verify import _ed_pub
from tools.zplug.verify import _ed_sign
from tools.zplug.verify import _excluded
from tools.zplug.verify import _find_distribution
from tools.zplug.verify import _freeze_stage
from tools.zplug.verify import _hash_file
from tools.zplug.verify import _hash_zip_member
from tools.zplug.verify import _normalize_mod_name
from tools.zplug.verify import _pin_installed_versions
from tools.zplug.verify import _pm_canonical
from tools.zplug.verify import _pm_split_requirement
from tools.zplug.verify import _pm_split_spec
from tools.zplug.verify import _PM_OK
from tools.zplug.verify import _resolve_bundle_modules
from tools.zplug.verify import _scan_stage_libs
from tools.zplug.verify import _sign_manifest
from tools.zplug.verify import _wheel_name_version
from tools.zplug.verify import _wheel_top_levels
from tools.zplug.verify import ARCH_CHOICES
from tools.zplug.verify import current_architecture
from tools.zplug.verify import DEFAULT_EXCLUDES
from tools.zplug.verify import lint_manifest
from tools.zplug.verify import list_installed_distributions
from tools.zplug.verify import load_source_manifest

if __name__ == "__main__":
    main()

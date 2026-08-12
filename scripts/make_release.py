"""Packaging helper — builds Vencertia_Decision_Runtime_<version>.zip.

Excludes: .git / caches / venvs / *.db / *.zip / coverage / docs build output.
"""

from __future__ import annotations

import os
import sys
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VERSION = "v1.1.1"
OUT = os.path.join(ROOT, f"Vencertia_Intelligence_Lab_{VERSION}.zip")

SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    ".codebuddy",
    ".workbuddy",
    ".idea",
    ".vscode",
    "htmlcov",
    "coverage",
}
SKIP_SUFFIXES = (".pyc", ".db", ".zip", ".pyo", ".sqlite", ".sqlite3")

# Additional directory names skipped for the v1.1.1 release (GAP: hygiene).
SKIP_DIRS |= {"cache", "data_cache", ".coverage"}


def main() -> int:
    zf = zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED)
    count = 0
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.endswith("__pycache__")]
        for name in files:
            if name.endswith(SKIP_SUFFIXES):
                continue
            path = os.path.join(base, name)
            rel = os.path.relpath(path, ROOT)
            zf.write(path, rel)
            count += 1
    zf.close()
    print(f"Wrote {OUT} ({count} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

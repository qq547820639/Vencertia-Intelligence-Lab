"""Packaging helper — builds Vencertia_Intelligence_Lab_<version>.zip.

Excludes: .git / caches / venvs / *.db / *.zip / coverage artifacts (incl. the
`.coverage` sqlite file, which is a FILE not a directory) / docs build output.
"""

from __future__ import annotations

import os
import re
import sys
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _runtime_version() -> str:
    """Read the single source of truth (``vencertia.__version__``) by parsing
    ``src/vencertia/__init__.py`` — no import side effects, no version drift
    between the release package name and the runtime it ships."""
    init_path = os.path.join(ROOT, "src", "vencertia", "__init__.py")
    with open(init_path, encoding="utf-8") as fh:
        for line in fh:
            match = re.search(r'^__version__\s*=\s*"([^"]+)"', line)
            if match:
                return match.group(1)
    raise SystemExit("src/vencertia/__init__.py does not declare __version__")


VERSION = "v" + _runtime_version()
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
    "cache",
    "data_cache",
}
SKIP_SUFFIXES = (".pyc", ".db", ".zip", ".pyo", ".sqlite", ".sqlite3")
# Coverage/CI artifacts that are FILES (a dir-name filter misses them).
SKIP_FILENAMES = {".coverage", "coverage.xml", "cobertura.xml", ".DS_Store"}


def _should_skip_file(name: str) -> bool:
    return name.endswith(SKIP_SUFFIXES) or name in SKIP_FILENAMES


def main() -> int:
    zf = zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED)
    count = 0
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.endswith("__pycache__")]
        for name in files:
            if _should_skip_file(name):
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

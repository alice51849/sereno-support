#!/usr/bin/env python3
"""Run the repository's exact-50 surface checker."""

from __future__ import annotations

import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parent
runpy.run_path(
    str(ROOT / "tools" / "check_required_surfaces.py"),
    run_name="__main__",
)

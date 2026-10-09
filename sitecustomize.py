"""Make the local ``src`` package importable when running from the project root.

This keeps commands such as ``python -m medpar_qa.cli`` working even before an
editable install has been completed. An editable install is still recommended.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

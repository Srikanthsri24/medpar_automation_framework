"""Launch pytest with the project reporting plugin and a timestamped report session."""
from __future__ import annotations

import subprocess
import sys


def main() -> int:
    """Run this script command-line workflow and return its process exit status. Launch pytest with
    the project reporting plugin and a timestamped report session.
    """
    return subprocess.call([sys.executable, "-m", "pytest", "-m", "regression", *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())

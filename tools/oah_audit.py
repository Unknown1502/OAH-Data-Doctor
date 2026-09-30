#!/usr/bin/env python
"""Standalone entry point: `python tools/oah_audit.py [audit|snapshot|gate0|...]`.

The master prompt referenced a seed script `tools/oah_audit.py`; it was not supplied with the brief, so this
script is the runnable seed that delegates to the packaged rules engine (docs/DECISIONS.md, D-003).
Works from a fresh clone without installation: it puts `backend/` on sys.path.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from datadoctor.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["audit", "--source", "auto"]))

#!/usr/bin/env python
"""Cross-platform task runner (Windows has no `make`). The Makefile delegates here.

    python tasks.py setup       create .venv, install backend + frontend, build the UI
    python tasks.py test        backend tests (unit, property, contract, integration)
    python tasks.py e2e         Playwright demo path + accessibility (needs `setup`)
    python tasks.py lint        ruff + mypy + TypeScript typecheck
    python tasks.py run         serve API + UI on http://127.0.0.1:8321 (DD_SOURCE: auto|live|snapshot)
    python tasks.py dev         API with reload + Vite dev server on :5173
    python tasks.py snapshot    fetch a new verified snapshot from the live sandbox
    python tasks.py audit       run an audit from the CLI (live with snapshot fallback)
    python tasks.py gate0       write docs/GATE0_REPORT.md from a live audit
    python tasks.py evaluate    fault-injection evaluation -> docs/EVALUATION.md
    python tasks.py offline     demo check with the network off: snapshot audit + e2e
    python tasks.py acceptance  expected outcomes of every API endpoint, against a running app (see scripts/acceptance.py)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
FRONT = ROOT / "frontend"
NPM = "npm.cmd" if os.name == "nt" else "npm"


def sh(cmd: list[str] | str, cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    print("$", cmd if isinstance(cmd, str) else " ".join(str(c) for c in cmd), flush=True)
    r = subprocess.run(cmd, cwd=cwd, env={**os.environ, **(env or {})}, shell=isinstance(cmd, str))
    if r.returncode:
        sys.exit(r.returncode)


def node_bin(pkg_path: str) -> list[str]:
    return ["node", str(FRONT / "node_modules" / pkg_path)]


def setup() -> None:
    if not PY.exists():
        venv.EnvBuilder(with_pip=True).create(VENV)
    sh([str(PY), "-m", "pip", "install", "--quiet", "-e", ".[dev]"])
    if shutil.which(NPM) is None:
        print("npm not found: install Node.js 20+ to build the UI (the API and CLI work without it).")
        return
    sh([NPM, "ci" if (FRONT / "package-lock.json").exists() else "install", "--no-audit", "--no-fund"], cwd=FRONT)
    sh(node_bin("vite/bin/vite.js") + ["build"], cwd=FRONT)


def test() -> None:
    sh([str(PY), "-m", "pytest", "backend/tests", "-q", "--cov=datadoctor", "--cov-report=term-missing:skip-covered"])


def e2e() -> None:
    sh(node_bin("vite/bin/vite.js") + ["build"], cwd=FRONT)  # the tests run against the served build: never a stale one
    sh(node_bin("@playwright/test/cli.js") + ["install", "chromium"], cwd=FRONT)
    sh(node_bin("@playwright/test/cli.js") + ["test"], cwd=FRONT, env={"CI": os.environ.get("CI", "")})


def lint() -> None:
    sh([str(PY), "-m", "ruff", "check", "backend", "scripts", "tools", "tasks.py"])
    sh([str(PY), "-m", "mypy"])
    sh(node_bin("typescript/bin/tsc") + ["-p", "tsconfig.json"], cwd=FRONT)


def run() -> None:
    if not (FRONT / "dist" / "index.html").exists():
        print("UI not built yet: run `python tasks.py setup` (the API still starts).")
    print("OAH Data Doctor: http://127.0.0.1:8321", flush=True)
    sh([str(PY), "-m", "uvicorn", "datadoctor.api.main:app", "--app-dir", "backend", "--host", "127.0.0.1", "--port", "8321"])


def dev() -> None:
    api = subprocess.Popen([str(PY), "-m", "uvicorn", "datadoctor.api.main:app", "--app-dir", "backend", "--port", "8321", "--reload"], cwd=ROOT)
    try:
        sh(node_bin("vite/bin/vite.js"), cwd=FRONT)
    finally:
        api.terminate()


def cli(*args: str) -> None:
    sh([str(PY), "tools/oah_audit.py", *args])


def offline() -> None:
    env = {"DD_SOURCE": "snapshot", "DD_STARTUP_LIVE": "0", "DD_FHIR_BASE": "http://127.0.0.1:9/unreachable"}
    sh([str(PY), "tools/oah_audit.py", "audit", "--source", "auto"], env=env)  # live fails -> verified snapshot fallback
    sh(node_bin("@playwright/test/cli.js") + ["test", "--project=desktop"], cwd=FRONT, env=env)


TASKS = {
    "setup": setup, "test": test, "e2e": e2e, "lint": lint, "run": run, "dev": dev, "offline": offline,
    "snapshot": lambda: cli("snapshot"), "audit": lambda: cli("audit", "--source", "auto"),
    "gate0": lambda: cli("gate0", "--source", "live"),
    "evaluate": lambda: sh([str(PY), "scripts/evaluate.py"]),
    "acceptance": lambda: sh([str(PY), "scripts/acceptance.py", *sys.argv[2:]]),
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in TASKS:
        print(__doc__)
        sys.exit(1)
    TASKS[sys.argv[1]]()

"""Go/no-go checks, landing projection and alert rules (frontend/src/checks.js), run in Node."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent


@pytest.mark.skipif(not shutil.which("node"), reason="node not on PATH (needed for the frontend anyway)")
def test_checks_and_alerts():
    r = subprocess.run(["node", str(HERE / "checks_check.mjs")], capture_output=True, text=True, timeout=60)
    results = json.loads(r.stdout.strip().splitlines()[-1])
    bad = [x for x in results if not x["ok"]]
    assert not bad, bad

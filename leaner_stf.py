"""Run cases through leanerSTFSpec (the Lean 4 STF spec) and collect results.

The comparison scripts hand a batch of `(kind, bytes)` cases to
`leaner/LeanerDecode.lean`, interpreted by `lake env lean --run` inside a built
leanerSTFSpec checkout, and get one `ACCEPT ...` / `REJECT ...` line back per
case.  The checkout is searched for in this order:

1. `$LEANER_STF_SPEC` if set,
2. `leanerSTFSpec/` beside this file (a checkout inside the repo),
3. `../leanerSTFSpec/` (this repo sitting next to a leanerSTFSpec checkout).

It must already be built (`lake build EthStateCommit EthCodec`).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
DRIVER = HERE / "leaner" / "LeanerDecode.lean"


def find_checkout() -> Path:
    """Return the leanerSTFSpec checkout root, or raise with instructions."""
    candidates = []
    env = os.environ.get("LEANER_STF_SPEC")
    if env:
        candidates.append(Path(env).expanduser().resolve())
    candidates.append(HERE / "leanerSTFSpec")
    candidates.append(HERE.parent / "leanerSTFSpec")

    for candidate in candidates:
        if (candidate / "STFSpec" / "StateCommit" / "AccountDecode.lean").is_file():
            return candidate

    tried = "\n  ".join(str(c) for c in candidates)
    raise SystemExit(
        "Could not find a leanerSTFSpec checkout.\nTried:\n  "
        f"{tried}\n\n"
        "Clone and build it, then point LEANER_STF_SPEC at it:\n"
        "  git clone https://github.com/alexanderlhicks/leanerSTFSpec.git\n"
        "  (cd leanerSTFSpec && lake build EthStateCommit EthCodec)\n"
        "  export LEANER_STF_SPEC=$PWD/leanerSTFSpec"
    )


def run_batch(cases: list[tuple[str, bytes]]) -> list[str]:
    """Decode every `(kind, bytes)` case with leanerSTFSpec, in order."""
    checkout = find_checkout()
    stdin = "".join(f"{kind} {data.hex()}\n" for kind, data in cases)
    proc = subprocess.run(
        ["lake", "env", "lean", "--run", str(DRIVER)],
        cwd=checkout,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )
    lines = proc.stdout.splitlines()
    if proc.returncode != 0 or len(lines) != len(cases):
        raise SystemExit(
            f"leanerSTFSpec driver failed (exit {proc.returncode}):\n"
            f"{proc.stdout}{proc.stderr}"
        )
    return lines

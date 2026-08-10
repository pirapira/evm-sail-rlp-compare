"""Locate the evm-sail Python extraction and put it on `sys.path`.

The comparison scripts import evm-sail's generated model directly from a
checkout rather than from a package, so they need to find that checkout. The
search order is:

1. `$EVM_SAIL` if set,
2. `evm-sail/` beside this file (a checkout inside the repo),
3. `../evm-sail/` (this repo sitting next to an evm-sail checkout).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def find_checkout() -> Path:
    """Return the evm-sail checkout root, or raise with instructions."""
    candidates = []
    env = os.environ.get("EVM_SAIL")
    if env:
        candidates.append(Path(env).expanduser().resolve())
    candidates.append(HERE / "evm-sail")
    candidates.append(HERE.parent / "evm-sail")

    for candidate in candidates:
        if (candidate / "extractions" / "python" / "src" / "evm").is_dir():
            return candidate

    tried = "\n  ".join(str(c) for c in candidates)
    raise SystemExit(
        "Could not find an evm-sail checkout containing "
        "extractions/python/src/evm.\nTried:\n  "
        f"{tried}\n\n"
        "Clone it and point EVM_SAIL at it:\n"
        "  git clone https://github.com/frisitano/evm-sail.git\n"
        "  export EVM_SAIL=$PWD/evm-sail"
    )


def add_extraction_to_sys_path() -> Path:
    """Prepend the extraction to `sys.path`; return the checkout root."""
    checkout = find_checkout()
    extraction = checkout / "extractions" / "python"
    for entry in (str(extraction), str(extraction / "src")):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    return checkout

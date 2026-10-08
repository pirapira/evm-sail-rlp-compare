"""Three-way result printing shared by the comparison scripts.

Two results agree when both reject, or when both accept with the same decoded
values.  Rejection reasons are not compared: each implementation reports them
in its own vocabulary.
"""

from __future__ import annotations

IMPLS = ("execution-specs", "evm-sail", "leanerSTFSpec")
SHORT = {"execution-specs": "specs", "evm-sail": "evm-sail", "leanerSTFSpec": "leaner"}


def outcome(result: str) -> str:
    """What two results must share to agree."""
    return result if result.startswith("ACCEPT") else "REJECT"


def agreement(results: tuple[str, str, str]) -> str:
    """`specs = leaner ≠ evm-sail`-style summary of which results agree."""
    groups: dict[str, list[str]] = {}
    for impl, result in zip(IMPLS, results):
        groups.setdefault(outcome(result), []).append(SHORT[impl])
    if len(groups) == 1:
        return "all agree"
    return " ≠ ".join(" = ".join(g) for g in groups.values())


def report(rows: list[tuple[str, str, str, bytes, str, str, str]]) -> int:
    """Print each `(name, note, label, input, specs, sail, leaner)` row and
    a per-pair disagreement count."""
    pairs = [(0, 1), (0, 2), (1, 2)]
    disagreements = {pair: 0 for pair in pairs}
    for name, note, label, data, *results in rows:
        results = tuple(results)
        summary = agreement(results)
        for i, j in pairs:
            if outcome(results[i]) != outcome(results[j]):
                disagreements[(i, j)] += 1
        print(f"{'  ' if summary == 'all agree' else '≠ '}{name}")
        print(f"    note            : {note}")
        print(f"    {label:<16}: {data.hex()}")
        for impl, result in zip(IMPLS, results):
            print(f"    {impl:<16}: {result}")
        print(f"    {'agreement':<16}: {summary}")
        print()
    print(f"{len(rows)} case(s). Disagreements by pair:")
    for i, j in pairs:
        print(f"  {SHORT[IMPLS[i]]} vs {SHORT[IMPLS[j]]}: {disagreements[(i, j)]}")
    return 0

"""Differential test: RLP scalar strictness on the storage-leaf decode path.

  execution-specs : ethereum.forks.amsterdam.witness_state.WitnessState.get_storage
                    (the leaf handling at witness_state.py:197-203; the trie
                    walk is stubbed to return the leaf under test)
  evm-sail        : evm.lib.state_trie.stateless_storage_by_key
                    (sail/lib/state_trie.sail:24; trie_lookup stubbed likewise)
  leanerSTFSpec   : STFSpec.StateCommit.decodeStorageLeaf
                    (STFSpec/StateCommit/StorageDecode.lean)

Usage:
    venv/bin/python compare_storage_leaf.py
"""

from __future__ import annotations

from evm_sail_path import add_extraction_to_sys_path
from leaner_stf import run_batch
from report import report

add_extraction_to_sys_path()

# --- evm-sail side -----------------------------------------------------------
import evm.HostContract as host  # noqa: E402
import evm.lib.rlp.decoding as sail_rlp  # noqa: E402
import evm.lib.state_trie as sail_state_trie  # noqa: E402
from evm._runtime import SailExit  # noqa: E402
from evm.primitives.bytes import stateless_input_slice  # noqa: E402

# --- execution-specs side ----------------------------------------------------
import ethereum.forks.amsterdam.witness_state as specs_ws  # noqa: E402
from ethereum_types.bytes import Bytes20, Bytes32  # noqa: E402

_reason: list[object] = []


def _recording_fatal_error(reason):
    _reason.append(reason)
    raise SailExit(None)


for _module in (sail_state_trie, sail_rlp):
    _module.fatal_error = _recording_fatal_error


def rlp_str(payload: bytes) -> bytes:
    if len(payload) == 1 and payload[0] < 0x80:
        return payload
    if len(payload) < 56:
        return bytes([0x80 + len(payload)]) + payload
    length = len(payload).to_bytes((len(payload).bit_length() + 7) // 8, "big")
    return bytes([0xB7 + len(length)]) + length + payload


def rlp_list(items: list[bytes]) -> bytes:
    payload = b"".join(items)
    if len(payload) < 56:
        return bytes([0xC0 + len(payload)]) + payload
    length = len(payload).to_bytes((len(payload).bit_length() + 7) // 8, "big")
    return bytes([0xF7 + len(length)]) + length + payload


# Any non-empty storage root makes both sides walk the trie; the walk itself is
# replaced, so the root, address and key values are irrelevant.
SOME_ROOT = Bytes32(b"\x11" * 32)
ADDRESS = Bytes20(b"\x22" * 20)
KEY = Bytes32(b"\x33" * 32)


def run_specs(leaf: bytes) -> str:
    state = object.__new__(specs_ws.WitnessState)
    state._storage_root_cache = {ADDRESS: SOME_ROOT}
    state._get_decoded_secure_root = lambda root: None
    original = specs_ws._trie_lookup
    specs_ws._trie_lookup = lambda node, key_hash: leaf
    try:
        return f"ACCEPT value={int(state.get_storage(ADDRESS, KEY))}"
    except Exception as exc:  # noqa: BLE001
        reason = " ".join(str(exc).split())
        return f"REJECT {type(exc).__name__}: {reason[:60]}"
    finally:
        specs_ws._trie_lookup = original


def run_sail(leaf: bytes) -> str:
    host.reset()
    host.get_state().stateless_input_bytes = leaf
    _reason.clear()
    original = sail_state_trie.trie.trie_lookup
    sail_state_trie.trie.trie_lookup = lambda root, path: stateless_input_slice(
        0, len(leaf)
    )
    try:
        value = sail_state_trie.stateless_storage_by_key(SOME_ROOT, KEY)
        return f"ACCEPT value={int(value)}"
    except BaseException as exc:  # noqa: BLE001
        cause = f"fatal_error({_reason[0]})" if _reason else type(exc).__name__
        return f"REJECT {cause}"
    finally:
        sail_state_trie.trie.trie_lookup = original


CASES: list[tuple[str, bytes, str]] = [
    ("canonical baseline", rlp_str(b"\x05"), "control: all must accept, value=5"),
    (
        "value with one leading zero byte",
        rlp_str(b"\x00\x05"),
        "0x820005 instead of 0x05",
    ),
    (
        "value 0 written as 0x00",
        b"\x00",
        "a zero slot is never stored; 0x00 is also non-canonical",
    ),
    (
        "value 0 written as 0x80",
        rlp_str(b""),
        "a zero slot is never stored, but this is the canonical zero",
    ),
    (
        "leaf is the empty list",
        rlp_list([]),
        "0xc0; specs and leaner map any list to 0",
    ),
    (
        "leaf is a non-empty list",
        rlp_list([rlp_str(b"\x05")]),
        "0xc105; specs and leaner map any list to 0",
    ),
    (
        "value of 2**256 - 1 behind a leading zero (33 bytes)",
        rlp_str(b"\x00" + b"\xff" * 32),
        "fits U256 numerically, but is 33 bytes long",
    ),
    (
        "value of 2**256",
        rlp_str((2**256).to_bytes(33, "big")),
        "control: overflows U256 everywhere",
    ),
    (
        "non-minimal framing",
        b"\x81\x05",
        "control: 0x8105 instead of the single byte 0x05",
    ),
    (
        "trailing byte after the item",
        rlp_str(b"\x05") + b"\x00",
        "0x0500: one item followed by garbage",
    ),
]


def main() -> int:
    leaner = run_batch([("storage", leaf) for _, leaf, _ in CASES])
    return report(
        [
            (name, note, "leaf rlp", leaf, run_specs(leaf), run_sail(leaf), lean)
            for (name, leaf, note), lean in zip(CASES, leaner)
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())

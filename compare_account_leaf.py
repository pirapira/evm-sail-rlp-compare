"""Differential test: RLP scalar strictness in evm-sail, execution-specs and
leanerSTFSpec.

All three decode account trie leaves out of the same stateless witness.  This
script feeds identical leaf encodings to each decoder and reports where they
disagree.

  execution-specs : ethereum.forks.amsterdam.witness_state._decode_account_from_leaf
  evm-sail        : evm.lib.rlp.codecs.state.decode_state_account
                    (sail/lib/rlp/codecs/state.sail:11)
  leanerSTFSpec   : STFSpec.StateCommit.decodeAccountLeaf
                    (STFSpec/StateCommit/AccountDecode.lean)

Usage:
    venv/bin/python compare_account_leaf.py
"""

from __future__ import annotations

from evm_sail_path import add_extraction_to_sys_path
from leaner_stf import run_batch
from report import report

add_extraction_to_sys_path()

# --- evm-sail side -----------------------------------------------------------
import evm.HostContract as host  # noqa: E402
import evm.lib.rlp.codecs.state as sail_state  # noqa: E402
import evm.lib.rlp.decoding as sail_rlp  # noqa: E402
from evm._runtime import SailExit  # noqa: E402
from evm.primitives.bytes import stateless_input_slice  # noqa: E402

# --- execution-specs side ----------------------------------------------------
from ethereum.forks.amsterdam.witness_state import (  # noqa: E402
    _decode_account_from_leaf,
)

# The extraction discards fatal_error's reason (it raises SailExit(None)).
# Recover it so a rejection can be attributed to a specific check.
_reason: list[object] = []


def _recording_fatal_error(reason):
    _reason.append(reason)
    raise SailExit(None)


for _module in (sail_state, sail_rlp):
    _module.fatal_error = _recording_fatal_error


# --- minimal RLP encoder (deliberately able to emit non-canonical forms) -----
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


ROOT32 = bytes.fromhex(
    "56e81f171bcc55a6ff8345e692c0f86e5b48e01b996cadc001622fb5e363b421"
)  # keccak256(rlp(b"")) - the empty trie root
CODE32 = bytes.fromhex(
    "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
)  # keccak256(b"") - the empty code hash


def leaf(nonce: bytes, balance: bytes, storage_root: bytes, code_hash: bytes) -> bytes:
    """An account leaf from four already-RLP-encoded fields."""
    return rlp_list([nonce, balance, storage_root, code_hash])


# --- the two decoders under test ---------------------------------------------
def sail_hash_hex(value) -> str:
    """Sail stores a `hash` vector least-significant byte first; undo that."""
    return bytes(reversed(bytes(value))).hex()


def run_specs(leaf_rlp: bytes) -> str:
    try:
        account, storage_root = _decode_account_from_leaf(leaf_rlp)
        return (
            f"ACCEPT nonce={int(account.nonce)} balance={int(account.balance)} "
            f"storage_root={storage_root.hex()} "
            f"code_hash={account.code_hash.hex()}"
        )
    except Exception as exc:  # noqa: BLE001
        reason = " ".join(str(exc).split())  # one line, however EELS words it
        return f"REJECT {type(exc).__name__}: {reason[:60]}"


def run_sail(leaf_rlp: bytes) -> str:
    host.reset()
    host.get_state().stateless_input_bytes = leaf_rlp
    _reason.clear()
    try:
        info = sail_state.decode_state_account(
            stateless_input_slice(0, len(leaf_rlp))
        )
        return (
            f"ACCEPT nonce={int(info.nonce)} balance={int(info.balance)} "
            f"storage_root={sail_hash_hex(info.storage_root)} "
            f"code_hash={sail_hash_hex(info.code_hash)}"
        )
    except BaseException as exc:  # noqa: BLE001
        cause = f"fatal_error({_reason[0]})" if _reason else type(exc).__name__
        return f"REJECT {cause}"


# --- the cases ---------------------------------------------------------------
CASES: list[tuple[str, bytes, str]] = [
    (
        "canonical baseline",
        leaf(rlp_str(b"\x01"), rlp_str(b"\x05"), rlp_str(ROOT32), rlp_str(CODE32)),
        "control: all must accept, nonce=1 balance=5",
    ),
    (
        "balance with one leading zero byte",
        leaf(
            rlp_str(b"\x01"), rlp_str(b"\x00\x05"), rlp_str(ROOT32), rlp_str(CODE32)
        ),
        "0x820005 instead of 0x05",
    ),
    (
        "nonce with one leading zero byte",
        leaf(
            rlp_str(b"\x00\x01"), rlp_str(b"\x05"), rlp_str(ROOT32), rlp_str(CODE32)
        ),
        "0x820001 instead of 0x01",
    ),
    (
        "balance encoded as 0x00 (should be empty string)",
        leaf(rlp_str(b"\x00"), rlp_str(b"\x00"), rlp_str(ROOT32), rlp_str(CODE32)),
        "zero written as 0x00, not 0x80",
    ),
    (
        "storage_root of 31 bytes",
        leaf(
            rlp_str(b"\x01"), rlp_str(b"\x05"), rlp_str(ROOT32[1:]), rlp_str(CODE32)
        ),
        "one byte short of a hash",
    ),
    (
        "code_hash of 31 bytes",
        leaf(
            rlp_str(b"\x01"), rlp_str(b"\x05"), rlp_str(ROOT32), rlp_str(CODE32[1:])
        ),
        "one byte short of a hash",
    ),
    (
        "storage_root of 33 bytes",
        leaf(
            rlp_str(b"\x01"),
            rlp_str(b"\x05"),
            rlp_str(b"\x00" + ROOT32),
            rlp_str(CODE32),
        ),
        "one byte over a hash",
    ),
    (
        "non-minimal framing on balance",
        leaf(rlp_str(b"\x01"), b"\x81\x05", rlp_str(ROOT32), rlp_str(CODE32)),
        "0x8105 instead of the single byte 0x05",
    ),
    (
        "nonce encoded as the empty list",
        leaf(rlp_list([]), rlp_str(b"\x05"), rlp_str(ROOT32), rlp_str(CODE32)),
        "0xc0 instead of 0x80; `if decoded[0]` treats [] as falsy",
    ),
    (
        "balance encoded as the empty list",
        leaf(rlp_str(b"\x01"), rlp_list([]), rlp_str(ROOT32), rlp_str(CODE32)),
        "0xc0 instead of 0x80",
    ),
    (
        "storage_root encoded as the empty list",
        leaf(rlp_str(b"\x01"), rlp_str(b"\x05"), rlp_list([]), rlp_str(CODE32)),
        "0xc0; specs and leaner substitute EMPTY_TRIE_ROOT",
    ),
    (
        "storage_root and code_hash as empty strings",
        leaf(rlp_str(b"\x01"), rlp_str(b"\x05"), rlp_str(b""), rlp_str(b"")),
        "control: all three substitute the empty-root/empty-code defaults",
    ),
    (
        "nonce of 2**64 (9 bytes, canonical)",
        leaf(
            rlp_str((2**64).to_bytes(9, "big")),
            rlp_str(b"\x05"),
            rlp_str(ROOT32),
            rlp_str(CODE32),
        ),
        "nonce is an unbounded Uint in specs and leaner, uint64 in evm-sail",
    ),
    (
        "balance of 2**256 - 1 behind a leading zero (33 bytes)",
        leaf(
            rlp_str(b"\x01"),
            rlp_str(b"\x00" + b"\xff" * 32),
            rlp_str(ROOT32),
            rlp_str(CODE32),
        ),
        "fits U256 numerically, but is 33 bytes long",
    ),
    (
        "balance of 2**256",
        leaf(
            rlp_str(b"\x01"),
            rlp_str((2**256).to_bytes(33, "big")),
            rlp_str(ROOT32),
            rlp_str(CODE32),
        ),
        "control: overflows U256 everywhere",
    ),
]


def main() -> int:
    leaner = run_batch([("account", leaf_rlp) for _, leaf_rlp, _ in CASES])
    return report(
        [
            (name, note, "leaf rlp", leaf_rlp, run_specs(leaf_rlp), run_sail(leaf_rlp), lean)
            for (name, leaf_rlp, note), lean in zip(CASES, leaner)
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())

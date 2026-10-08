"""Differential test: RLP scalar strictness on the transaction decode path.

  execution-specs : ethereum.forks.amsterdam.transactions.decode_transaction
                    (rlp.decode_to against dataclasses whose fields are typed
                    U256 / Address, so every scalar is checked for canonicality
                    and every fixed-width field for exact length)
  evm-sail        : evm.lib.rlp.codecs.transactions.rlp_decode_tx
                    (sail/lib/rlp/codecs/transactions.sail)
  leanerSTFSpec   : no transaction decoder yet (EthBlock is scaffolding), so
                    leaner/LeanerDecode.lean applies its typed RLP field
                    adapters (STFSpec/Codec/RlpTyped.lean) to the EELS
                    FeeMarketTransaction schema, field by field

Usage:
    venv/bin/python compare_transaction.py
"""

from __future__ import annotations

from evm_sail_path import add_extraction_to_sys_path
from leaner_stf import run_batch
from report import report

add_extraction_to_sys_path()

import evm.HostContract as host  # noqa: E402
import evm.lib.rlp.codecs.transactions as sail_tx  # noqa: E402
import evm.lib.rlp.decoding as sail_rlp  # noqa: E402
from evm._runtime import SailExit  # noqa: E402
from evm.primitives.bytes import stateless_input_slice  # noqa: E402

from ethereum.forks.amsterdam.transactions import decode_transaction  # noqa: E402

_reason: list[object] = []


def _recording_fatal_error(reason):
    _reason.append(reason)
    raise SailExit(None)


for _module in (sail_tx, sail_rlp):
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


TO20 = bytes.fromhex("1111111111111111111111111111111111111111")
R = rlp_str(bytes.fromhex("11" * 32))
S = rlp_str(bytes.fromhex("22" * 32))


def fee_market_tx(
    *,
    to: bytes = rlp_str(TO20),
    y_parity: bytes = rlp_str(b""),
) -> bytes:
    """A type-2 (EIP-1559) transaction: 0x02 || rlp([...12 fields...])."""
    return b"\x02" + rlp_list(
        [
            rlp_str(b"\x01"),  # chain_id
            rlp_str(b"\x00"[1:]),  # nonce = 0, canonical empty string
            rlp_str(b"\x01"),  # max_priority_fee_per_gas
            rlp_str(b"\x02"),  # max_fee_per_gas
            rlp_str(b"\x52\x08"),  # gas = 21000
            to,  # to
            rlp_str(b""),  # value = 0
            rlp_str(b""),  # data
            rlp_list([]),  # access_list
            y_parity,  # y_parity
            R,  # r
            S,  # s
        ]
    )


# A 65-byte uncompressed public key; evm-sail derives `sender` from it at
# decode time but performs no verification there, so any well-formed value
# exercises the same decode path.
PUBKEY = b"\x04" + bytes(range(64))


def run_specs(tx_bytes: bytes) -> str:
    try:
        tx = decode_transaction(tx_bytes)
        return (
            f"ACCEPT y_parity={int(tx.y_parity)} to=0x{bytes(tx.to).hex()}"
        )
    except Exception as exc:  # noqa: BLE001
        reason = " ".join(str(exc).split())  # one line, however EELS words it
        return f"REJECT {type(exc).__name__}: {reason[:70]}"


def run_sail(tx_bytes: bytes) -> str:
    host.reset()
    host.get_state().stateless_input_bytes = tx_bytes + PUBKEY
    _reason.clear()
    try:
        fields = sail_tx.rlp_decode_tx(
            stateless_input_slice(0, len(tx_bytes)),
            stateless_input_slice(len(tx_bytes), len(PUBKEY)),
            6,  # blob_limit, unused for type 2
        )
        recipient = bytes(reversed(bytes(fields.recipient))).hex()
        return f"ACCEPT y_parity={int(fields.sig_v)} to=0x{recipient}"
    except BaseException as exc:  # noqa: BLE001
        cause = f"fatal_error({_reason[0]})" if _reason else type(exc).__name__
        return f"REJECT {cause}"


CASES: list[tuple[str, bytes, str]] = [
    (
        "canonical baseline",
        fee_market_tx(),
        "y_parity 0 as the empty string, 20-byte to",
    ),
    (
        "y_parity encoded as 0x00",
        fee_market_tx(y_parity=b"\x00"),
        "a leading (and only) zero byte instead of 0x80",
    ),
    (
        "y_parity 1 with a leading zero byte",
        fee_market_tx(y_parity=rlp_str(b"\x00\x01")),
        "0x820001 instead of 0x01",
    ),
    (
        "to of 19 bytes",
        fee_market_tx(to=rlp_str(TO20[1:])),
        "one byte short of an address",
    ),
    (
        "to of 21 bytes",
        fee_market_tx(to=rlp_str(b"\xaa" + TO20)),
        "one byte over an address",
    ),
]


def main() -> int:
    leaner = run_batch([("tx", tx_bytes) for _, tx_bytes, _ in CASES])
    return report(
        [
            (name, note, "tx bytes", tx_bytes, run_specs(tx_bytes), run_sail(tx_bytes), lean)
            for (name, tx_bytes, note), lean in zip(CASES, leaner)
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())

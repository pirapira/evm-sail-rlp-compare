# RLP scalar strictness: evm-sail vs execution-specs

**Question.** Do the two implementations apply the same leading-zero / canonicality
rules to RLP-encoded numbers at corresponding decode sites?

**Answer: no.** They disagree at three of the four sites examined, and they
disagree *in both directions* — there are encodings execution-specs accepts and
evm-sail rejects, and encodings evm-sail accepts and execution-specs rejects.
Nine concrete witnesses are given below, all executed against both
implementations.

Pinned revisions: evm-sail `45fc3fce902fe4853e9d53bfafe2446ed5ab51aa`;
execution-specs `e5a8caf1b8055e4d805c7fb169edfa710914b7da` (`projects/zkevm`),
`ethereum-rlp` 0.1.6.

---

## 1. The two rule sets

### evm-sail has two scalar decoders, one strict and one lax

`sail/lib/rlp/decoding.sail` defines the strictness predicate
`rlp_item_uint_canonical` (line 444): canonical framing **and** no leading zero
byte.

| function | line | framing checked | leading zero rejected | length rule |
| --- | --- | --- | --- | --- |
| `rlp_decode_u256` | 502 | yes | yes | `≤ 32` |
| `rlp_decode_uint64` | 516 | yes | yes | `≤ 8` |
| `rlp_decode_bool` | 545 | yes | yes | value ∈ {0,1} |
| **`rlp_decode_word`** | **487** | **no** | **no** | **`≤ 32`, silently zero-extends** |

`rlp_decode_word` checks only `not is_list` and `content_len ≤ 32`, then
`slice_load_n` right-aligns the content in a 256-bit word. A short field is
zero-extended on the left; a field of 21–32 bytes that is later narrowed by
`word_to_address` (`sail/prelude.sail:170`) is **truncated to its low 20 bytes**.

The non-throwing predicates `rlp_word_valid`, `rlp_u256_valid` and
`rlp_uint64_valid` (lines 459–483) exist but have **no call sites anywhere in
`sail/`** — the intended strict-validation pass is not wired up.

### execution-specs is strict — except on the account leaf

`ethereum_rlp.rlp` is uniformly strict:

- `_deserialize_to_uint` (rlp.py:265): `if len(decoded) > 0 and decoded[0] == 0:
  raise DecodingError("non-canonical integer")`
- `_deserialize_to_bytes` (rlp.py:255): `class_(value)`, and `FixedBytes`
  raises `ValueError: expected 32 bytes but got 31` on a length mismatch
- `decode_to_bytes` (rlp.py:387) rejects non-minimal framing and trailing bytes

**But the witness account-leaf decoder bypasses all of it.**
`ethereum/forks/amsterdam/witness_state.py:100`:

```python
decoded = rlp.decode(leaf_value)              # structural only
nonce = Uint(int.from_bytes(decoded[0], "big")) if decoded[0] else Uint(0)
balance = U256(int.from_bytes(decoded[1], "big")) if decoded[1] else U256(0)
storage_root = Root(decoded[2]) if decoded[2] else EMPTY_TRIE_ROOT
code_hash = Hash32(decoded[3]) if decoded[3] else EMPTY_CODE_HASH
```

`int.from_bytes` accepts leading zeros. So on this one path execution-specs is
*laxer* than its own `decode_to`, and laxer than evm-sail.

## 2. Site-by-site comparison

| Decode site | execution-specs | evm-sail | agree? |
| --- | --- | --- | --- |
| Account trie leaf — `nonce`, `balance` | `int.from_bytes`, **lax** | `rlp_decode_uint64` / `rlp_decode_u256`, strict | **no** |
| Account trie leaf — `storage_root`, `code_hash` | `Root`/`Hash32`, exact 32 | `rlp_decode_word`, **`≤ 32`** | **no** |
| Transaction — `y_parity` / `v` | `U256`, strict | `rlp_decode_word`, **lax** | **no** |
| Transaction — `to` | `Address`, exact 20 | `rlp_decode_word` + `word_to_address`, **`≤ 32`** | **no** |
| Transaction — `nonce`, `value`, `r`, `s`, fees, `chain_id` | `U256`/`Uint`, strict | `rlp_decode_u256` / `rlp_decode_uint64`, strict | yes |
| Access-list `address` and storage keys | `Address` / `Bytes32`, exact | `rlp_decode_word`, **`≤ 32`** | **no** (by inspection) |
| Witness parent header — `parent_hash`, `state_root` | `Hash32`/`Root`, exact 32 | `rlp_decode_word` (`sail/lib/ssz/stateless_input.sail:708,712`) | **no** (by inspection) |
| Witness parent header — `base_fee`, blob gas fields | `Uint`, strict | `rlp_decode_u256` / `rlp_decode_uint64`, strict | yes |
| Block access list — all scalars | strict | `bal_ref_word` / `bal_ref_uint64` wrap the lax decoder in an explicit `rlp_item_uint_canonical` check (`sail/lib/rlp/codecs/block_access_list.sail:36-59`) | yes |

The BAL codec is the pattern the other two sites are missing: it calls
`rlp_decode_word` but guards it with the canonicality predicate first.

## 3. Experimental witnesses

Run:

```bash
venv/bin/python compare_account_leaf.py
venv/bin/python compare_transaction.py
```

Setup is in [§5](#5-reproducing). Saved output: `output-account-leaf.txt`,
`output-transaction.txt`.

### 3.1 Account trie leaf — `_decode_account_from_leaf` vs `decode_state_account`

Baseline (both accept, `nonce=1 balance=5`):

```
f8440105a056e81f171bcc55a6ff8345e692c0f86e5b48e01b996cadc001622fb5e363b421
a0c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470
```

**W1 — balance with a leading zero byte** (`0x820005` for 5).
execution-specs: `ACCEPT balance=5`. evm-sail: `REJECT fatal_error(RlpDecode)`.

```
f84601820005a056e81f171bcc55a6ff8345e692c0f86e5b48e01b996cadc001622fb5e363b421a0c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470
```

**W2 — nonce with a leading zero byte** (`0x820001` for 1).
execution-specs: `ACCEPT nonce=1`. evm-sail: `REJECT fatal_error(RlpDecode)`.

```
f84682000105a056e81f171bcc55a6ff8345e692c0f86e5b48e01b996cadc001622fb5e363b421a0c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470
```

**W3 — zero written as `0x00` rather than `0x80`** (both nonce and balance).
execution-specs: `ACCEPT nonce=0 balance=0`. evm-sail: `REJECT fatal_error(RlpDecode)`.

```
f8440000a056e81f171bcc55a6ff8345e692c0f86e5b48e01b996cadc001622fb5e363b421a0c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470
```

**W4 — 31-byte `storage_root`.**
execution-specs: `REJECT ValueError: expected 32 bytes but got 31`.
evm-sail: **`ACCEPT`**, with the root silently zero-extended to
`00e81f171bcc55a6ff8345e692c0f86e5b48e01b996cadc001622fb5e363b421`.

```
f84301059fe81f171bcc55a6ff8345e692c0f86e5b48e01b996cadc001622fb5e363b421a0c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470
```

**W5 — 31-byte `code_hash`.** Same shape: specs rejects, evm-sail accepts with
`code_hash = 00d2460186f7…`.

```
f8430105a056e81f171bcc55a6ff8345e692c0f86e5b48e01b996cadc001622fb5e363b4219fd2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470
```

Agreeing controls: a 33-byte `storage_root` and non-minimal framing
(`0x8105` for 5) are rejected by both.

### 3.2 Transaction — `decode_transaction` vs `rlp_decode_tx`

All cases are type-2 (EIP-1559) transactions. Baseline (both accept,
`y_parity=0`, `to=0x1111…11`):

```
02f862018001028252089411111111111111111111111111111111111111118080c080
a01111111111111111111111111111111111111111111111111111111111111111
a02222222222222222222222222222222222222222222222222222222222222222
```

**W6 — `y_parity` encoded as `0x00`** instead of the empty string `0x80`.
execution-specs: `REJECT DecodingError` (non-canonical integer).
evm-sail: **`ACCEPT y_parity=0`**.

```
02f862018001028252089411111111111111111111111111111111111111118080c000a01111111111111111111111111111111111111111111111111111111111111111a02222222222222222222222222222222222222222222222222222222222222222
```

**W7 — `y_parity = 1` with a leading zero byte** (`0x820001`).
execution-specs: `REJECT DecodingError`. evm-sail: **`ACCEPT y_parity=1`**.

```
02f864018001028252089411111111111111111111111111111111111111118080c0820001a01111111111111111111111111111111111111111111111111111111111111111a02222222222222222222222222222222222222222222222222222222222222222
```

**W8 — 19-byte `to`.** execution-specs: `REJECT DecodingError`.
evm-sail: **`ACCEPT`** with `to = 0x0011111111111111111111111111111111111111`
(zero-extended).

```
02f8610180010282520893111111111111111111111111111111111111118080c080a01111111111111111111111111111111111111111111111111111111111111111a02222222222222222222222222222222222222222222222222222222222222222
```

**W9 — 21-byte `to`** (`0xaa` prepended). execution-specs: `REJECT
DecodingError`. evm-sail: **`ACCEPT`** with `to =
0x1111111111111111111111111111111111111111` — the leading byte is silently
**truncated**, so this transaction and the baseline decode to the same
recipient while having different bytes and different transaction hashes.

```
02f8630180010282520895aa11111111111111111111111111111111111111118080c080a01111111111111111111111111111111111111111111111111111111111111111a02222222222222222222222222222222222222222222222222222222222222222
```

## 4. Why each direction matters

**evm-sail stricter than specs (W1–W3, account leaf).** A witness containing an
account leaf whose `balance` or `nonce` carries a leading zero is accepted by
execution-specs and rejected by evm-sail. This is the *same fixture shape as
PR #3193*: the witness supplier chooses the leaf bytes, and re-roots the parent
header so the trie is self-consistent. Where PR #3193 asserts the Python
decoder accepts an over-length path, W1 asserts it accepts a non-canonical
integer — and here evm-sail is the one that halts. For a stateless guest this
is a liveness/completeness failure: a payload the spec calls valid cannot be
proven.

**specs stricter than evm-sail (W4–W9).** evm-sail accepts encodings the spec
rejects, and worse, *reinterprets* them: W4/W5 change a hash by zero-extension,
W8 changes an address by zero-extension, W9 discards a byte. These are
soundness failures — evm-sail would validate a block that execution-specs (and
therefore the network) considers invalid. W9 is the sharpest: two distinct
transaction encodings, with distinct hashes, map to the same execution.

The transaction cases sit behind signature recovery: evm-sail takes the sender
from a witness-supplied public key and computes the signing hash over the raw
byte span, so W6–W9 require a signer who actually signed the malformed
encoding. That is a real scenario — nothing stops a signer from emitting one —
but it is not reachable by an attacker mutating someone else's transaction.
The account-leaf and header cases have no such gate.

**Suggested fix shape.** Every `rlp_decode_word` call site outside the BAL codec
needs the guard the BAL codec already applies: `rlp_item_uint_canonical` for
integer fields, and an exact `content_len` check (32 for hashes, 20 for
addresses) for fixed-width fields. The unused `rlp_word_valid` / `rlp_u256_valid`
predicates suggest this was the intent.

## 5. Reproducing

```bash
# the two implementations, cloned beside this repo (or inside it)
git clone https://github.com/frisitano/evm-sail.git
git -C evm-sail checkout 45fc3fce902fe4853e9d53bfafe2446ed5ab51aa
git clone https://github.com/ethereum/execution-specs.git
git -C execution-specs checkout e5a8caf1b8055e4d805c7fb169edfa710914b7da

# one venv holding both sides.  Python 3.12: execution-specs pulls in
# coincurve, which has no wheel for 3.14 and fails to build there.
python3.12 -m venv venv
venv/bin/pip install -e ./execution-specs pydantic

venv/bin/python compare_account_leaf.py
venv/bin/python compare_transaction.py
```

evm-sail's side is its checked-in Python extraction
(`evm-sail/extractions/python/src/evm/`), imported by path — no Sail build
needed. `evm_sail_path.py` finds the checkout at `./evm-sail`, then
`../evm-sail`, then `$EVM_SAIL`.

Two harness details worth knowing if you extend the scripts:

- The extraction discards `fatal_error`'s reason (it raises `SailExit(None)`),
  so both scripts monkey-patch `fatal_error` to record the `FatalError` enum
  value. Code `2` is `RlpDecode`.
- Sail's `hash`/`address` vectors are stored least-significant byte first, so
  hex printing must reverse them (`sail_hash_hex`). Without this the control
  rows look like mismatches when they are not.

## 6. Files

| File | Contents |
| --- | --- |
| `RLP-SCALAR-DIVERGENCE.md` | This document |
| `compare_account_leaf.py` | Witnesses W1–W5 plus agreeing controls |
| `compare_transaction.py` | Witnesses W6–W9 plus the baseline |
| `evm_sail_path.py` | Locates the evm-sail extraction |
| `output-account-leaf.txt`, `output-transaction.txt` | Saved runs |

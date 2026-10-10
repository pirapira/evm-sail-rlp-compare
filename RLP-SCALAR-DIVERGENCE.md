# RLP scalar strictness: evm-sail vs execution-specs vs leanerSTFSpec

**Question.** Do the three specifications of the stateless guest apply the same
leading-zero / canonicality rules to RLP-encoded numbers at corresponding decode
sites?

**Answer.** evm-sail disagrees with execution-specs at most of the sites
examined (§2), in *both directions*: some encodings are accepted by
execution-specs and rejected by evm-sail, and some the other way round.
**leanerSTFSpec agrees with execution-specs on every case, accepted values
included** (§6). It deliberately reproduces execution-specs' lenient leaf
decoders. Every divergence below is therefore execution-specs + leanerSTFSpec
on one side and evm-sail on the other.

Eighteen witnesses are given, all executed against all three: W1–W9 from the
original two-way comparison, plus W10–W18, found by reading leanerSTFSpec's
account and storage leaf contracts (§6.3).

Pinned revisions: evm-sail `adc44afd21ef6d5a45c96046f0d23f527acbf54e`;
execution-specs `e1a316a06fc3d3e0a5da36fdc78580811e9d8a36` (`tests-zkevm@v21.0.0`,
the normative target leanerSTFSpec pins in its `reference.toml`), `ethereum-rlp`
0.1.6; leanerSTFSpec `daa6a8a4e13e3ce9e54c3b4da6f60dac7ac42de0`. W1–W9 were
first found against evm-sail `45fc3fc` and execution-specs `e5a8caf`. They
reproduce byte-for-byte at the current pins, and the leaf-decoding code in
`witness_state.py` is unchanged between the two execution-specs commits.

---

## 1. The rule sets of evm-sail and execution-specs

leanerSTFSpec follows execution-specs at every site it specifies; its rule set is in [§6.1](#61-rule-set-by-reading).

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
`ethereum/forks/amsterdam/witness_state.py:103`:

```python
decoded = rlp.decode(leaf_value)              # structural only
nonce = Uint(int.from_bytes(decoded[0], "big")) if decoded[0] else Uint(0)
balance = U256(int.from_bytes(decoded[1], "big")) if decoded[1] else U256(0)
storage_root = Root(decoded[2]) if decoded[2] else EMPTY_TRIE_ROOT
code_hash = Hash32(decoded[3]) if decoded[3] else EMPTY_CODE_HASH
```

`int.from_bytes` accepts leading zeros. So on this one path execution-specs is
*laxer* than its own `decode_to`, and laxer than evm-sail. Python truthiness
adds a second leniency: the empty *list* `0xc0` is falsy, just like the empty
string, so any field written as `0xc0` takes its default. The storage-leaf
decoder (`witness_state.py:198–203`) is lax in the same ways, and it also
maps *any* list, empty or not, to zero.

## 2. Site-by-site comparison

| Decode site | execution-specs | evm-sail | leanerSTFSpec | specs = evm-sail? |
| --- | --- | --- | --- | --- |
| Account trie leaf — `nonce`, `balance` | `int.from_bytes`, **lax** | `rlp_decode_uint64` / `rlp_decode_u256`, strict | = specs (proved, `decodeAccountLeaf_eq_ok_iff`) | **no** |
| Account trie leaf — `nonce` width | `Uint`, unbounded | `rlp_decode_uint64`, `≤ 8` bytes | = specs (`Nat`) | **no** |
| Account trie leaf — `storage_root`, `code_hash` | `Root`/`Hash32`, exact 32 | `rlp_decode_word`, **`≤ 32`** | = specs | **no** |
| Storage trie leaf | `int.from_bytes`, **lax**; any list → 0 | `rlp_decode_u256`, strict | = specs | **no** |
| Transaction — `y_parity` / `v` | `U256`, strict | `rlp_decode_word`, **lax** | = specs (field adapters only) | **no** |
| Transaction — `to` | `Address`, exact 20 | `rlp_decode_word` + `word_to_address`, **`≤ 32`** | = specs (field adapters only) | **no** |
| Transaction — `nonce`, `value`, `r`, `s`, fees, `chain_id` | `U256`/`Uint`, strict | `rlp_decode_u256` / `rlp_decode_uint64`, strict | = specs (field adapters only) | yes |
| Access-list `address` and storage keys | `Address` / `Bytes32`, exact | `rlp_decode_word`, **`≤ 32`** | not yet specified | **no** (by inspection) |
| Witness parent header — `parent_hash`, `state_root` | `Hash32`/`Root`, exact 32 | `rlp_decode_word` (`sail/lib/ssz/stateless_input.sail:708,712`) | not yet specified | **no** (by inspection) |
| Witness parent header — `base_fee`, blob gas fields | `Uint`, strict | `rlp_decode_u256` / `rlp_decode_uint64`, strict | not yet specified | yes |
| Block access list — all scalars | strict | `bal_ref_word` / `bal_ref_uint64` wrap the lax decoder in an explicit `rlp_item_uint_canonical` check (`sail/lib/rlp/codecs/block_access_list.sail:36-59`) | not yet specified | yes |

The BAL codec is the pattern the other two sites are missing: it calls
`rlp_decode_word` but guards it with the canonicality predicate first.

## 3. Experimental witnesses

Run:

```bash
venv/bin/python compare_account_leaf.py
venv/bin/python compare_transaction.py
venv/bin/python compare_storage_leaf.py
```

Setup is in [§5](#5-reproducing). Saved output: `output-account-leaf.txt`,
`output-transaction.txt`, `output-storage-leaf.txt`. In every witness below,
leanerSTFSpec's result is identical to execution-specs'.

### 3.1 Account trie leaf — `_decode_account_from_leaf` vs `decode_state_account`

Baseline (all three accept, `nonce=1 balance=5`):

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

Agreeing controls: a 33-byte `storage_root`, non-minimal framing
(`0x8105` for 5) and a balance of 2²⁵⁶ are rejected by all three. A
`storage_root` written as `0xc0`, and empty-string root and code hash, are
accepted by all three as the empty-trie / empty-code defaults. evm-sail takes
the default whenever `content_len == 0` and never checks `is_list` on that
branch, which is why it agrees here.

**W10 — nonce written as the empty list `0xc0`.** execution-specs and
leanerSTFSpec: `ACCEPT nonce=0`. evm-sail: `REJECT fatal_error(RlpDecode)`.

```
f844c005a056e81f171bcc55a6ff8345e692c0f86e5b48e01b996cadc001622fb5e363b421a0c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470
```

**W11 — balance written as the empty list `0xc0`.** Same shape:
`ACCEPT balance=0` vs `REJECT`.

```
f84401c0a056e81f171bcc55a6ff8345e692c0f86e5b48e01b996cadc001622fb5e363b421a0c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470
```

**W12 — nonce 2⁶⁴, canonically encoded (9 bytes).** execution-specs and
leanerSTFSpec: `ACCEPT nonce=18446744073709551616` (nonce is an unbounded
`Uint` / `Nat`). evm-sail: `REJECT` (`rlp_decode_uint64`, `≤ 8` bytes). Unlike
the other witnesses, this one is canonical RLP. The disagreement is about the
nonce's *type*, not about strictness. EIP-2681 makes 2⁶⁴ − 1 the maximum
reachable nonce, so a valid chain never produces this leaf. leanerSTFSpec's
`Account.nonce` documents the choice: "transaction admission owns nonce
limits".

```
f84d8901000000000000000005a056e81f171bcc55a6ff8345e692c0f86e5b48e01b996cadc001622fb5e363b421a0c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470
```

**W13 — balance 2²⁵⁶ − 1 behind a leading zero (33 bytes).** execution-specs and
leanerSTFSpec accept, because the bound is numerical rather than a byte count.
evm-sail rejects. This is the W1 class at the width boundary.

```
f86501a100ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffa056e81f171bcc55a6ff8345e692c0f86e5b48e01b996cadc001622fb5e363b421a0c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470
```

### 3.2 Transaction — `decode_transaction` vs `rlp_decode_tx`

All cases are type-2 (EIP-1559) transactions. Baseline (all three accept,
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

### 3.3 Storage trie leaf — `WitnessState.get_storage` vs `stateless_storage_by_key`

Both sides run their real lookup function, with only the trie walk stubbed out
to return the leaf under test. Baseline `05` and canonical zero `80` are accepted
by all three. Controls rejected by all three: 2²⁵⁶, non-minimal `8105`, and a
trailing byte `0500`.

| | leaf | execution-specs = leanerSTFSpec | evm-sail |
| --- | --- | --- | --- |
| **W14** | `820005` (leading zero) | `ACCEPT value=5` | `REJECT` |
| **W15** | `00` (zero as `0x00`) | `ACCEPT value=0` | `REJECT` |
| **W16** | `c0` (empty list) | `ACCEPT value=0` | `REJECT` |
| **W17** | `c105` (non-empty list) | `ACCEPT value=0` | `REJECT` |
| **W18** | `a100ff…ff` (2²⁵⁶ − 1, 33 bytes) | `ACCEPT value=2²⁵⁶−1` | `REJECT` |

W17 is the most permissive: execution-specs (`witness_state.py:203`, `return
U256(0)` for any non-bytes decode) and leanerSTFSpec (`decodeStorageLeaf`,
`| .ok (.list _) => .ok U256.zero`) both read any list-valued leaf as an
empty slot.

## 4. Why each direction matters

**evm-sail stricter than specs (W1–W3, W10–W18, account and storage leaves).** A witness containing an
account leaf whose `balance` or `nonce` carries a leading zero is accepted by
execution-specs and rejected by evm-sail. This is the *same fixture shape as
PR #3193*: the witness supplier chooses the leaf bytes, and re-roots the parent
header so the trie is self-consistent. Where PR #3193 asserts the Python
decoder accepts an over-length path, W1 asserts it accepts a non-canonical
integer — and here evm-sail is the one that halts. For a stateless guest this
is a liveness/completeness failure: a payload the spec calls valid cannot be
proven.

leanerSTFSpec assesses reachability differently. Its `EthStateCommit` spec
(§7.2, SC10) argues that "lenient decodings are collision-guarded": a leaf is
part of an authenticated trie node, so a non-canonical leaf under the same
root as a well-formed state implies a Keccak collision. Both claims hold, in
different settings. Against a pre-state root that the verifier trusts, the
leaf is collision-guarded. A self-consistent witness that re-roots its own
parent header (the fixture setting above) still reaches the leaf. In both
settings, evm-sail fails on inputs that the other two specifications accept.

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
# the three implementations, cloned beside this repo (or inside it)
git clone https://github.com/frisitano/evm-sail.git
git -C evm-sail checkout adc44afd21ef6d5a45c96046f0d23f527acbf54e
git clone https://github.com/ethereum/execution-specs.git
git -C execution-specs fetch origin e1a316a06fc3d3e0a5da36fdc78580811e9d8a36
git -C execution-specs checkout e1a316a06fc3d3e0a5da36fdc78580811e9d8a36
git clone https://github.com/alexanderlhicks/leanerSTFSpec.git
git -C leanerSTFSpec checkout daa6a8a4e13e3ce9e54c3b4da6f60dac7ac42de0
(cd leanerSTFSpec && lake build EthStateCommit EthCodec)   # elan fetches Lean v4.34.0

# one venv holding the two Python sides.  Python 3.12: execution-specs pulls in
# coincurve, which has no wheel for 3.14 and fails to build there.  Pin
# ethereum-rlp to the version execution-specs' uv.lock locks.
python3.12 -m venv venv
venv/bin/pip install -e ./execution-specs pydantic ethereum-rlp==0.1.6

venv/bin/python compare_account_leaf.py
venv/bin/python compare_transaction.py
venv/bin/python compare_storage_leaf.py
```

leanerSTFSpec's side is `leaner/LeanerDecode.lean`, run by `leaner_stf.py`
with `lake env lean --run` inside the built checkout. It reads one `<kind>
<hex>` case per line and prints one result per line. `leaner_stf.py` finds the
checkout at `$LEANER_STF_SPEC`, then `./leanerSTFSpec`, then
`../leanerSTFSpec`.

evm-sail's side is its checked-in Python extraction
(`evm-sail/extractions/python/src/evm/`), imported by path — no Sail build
needed. `evm_sail_path.py` finds the checkout at `./evm-sail`, then
`../evm-sail`, then `$EVM_SAIL`.

Two harness details worth knowing if you extend the scripts:

- The extraction discards `fatal_error`'s reason (it raises `SailExit(None)`),
  so the scripts monkey-patch `fatal_error` to record the `FatalError` enum
  value. Code `2` is `RlpDecode`.
- Sail's `hash`/`address` vectors are stored least-significant byte first, so
  hex printing must reverse them (`sail_hash_hex`). Without this the control
  rows look like mismatches when they are not.

## 6. leanerSTFSpec

[leanerSTFSpec](https://github.com/alexanderlhicks/leanerSTFSpec) is an
executable Lean 4 specification of the same stateless guest. It targets
`tests-zkevm@v21.0.0`, and evm-asm and stateless-pancaketh are to be verified
against it. Its lower layers (bytes, hashing, RLP, MPT, the state/commitment
seam) are implemented; `EthBlock` and `EthStateless` are still scaffolding.

### 6.1 Rule set, by reading

| Site | leanerSTFSpec | Compared with execution-specs |
| --- | --- | --- |
| Generic RLP (`Codec/RlpDecode.lean`) | strict: canonical framing, no trailing bytes | same |
| Typed integer (`Codec/RlpTyped.lean:28`, `integer`) | rejects lists, then a leading zero byte, then over-width | same order as `ethereum_rlp` 0.1.6 / `ethereum_types` 0.4.1 |
| Fixed bytes (`toFixed`, line 63) | exact length | same as `FixedBytes` |
| `Bytes0 \| Address` (`union2`, line 87) | exactly one variant must succeed | same as `rlp.py:325–343` |
| Account leaf (`StateCommit/AccountDecode.lean:214`, `decodeAccountLeaf`) | lenient by design: leading zeros accepted; empty string *or empty list* → default; nonce unbounded; balance bounded numerically; hashes exact 32 when non-empty | same: spec item SC5, citing `witness_state.py:103–127` |
| Storage leaf (`StateCommit/StorageDecode.lean:92`, `decodeStorageLeaf`) | lenient by design: leading zeros accepted; any list → 0; numerical bound 2²⁵⁶ | same: SC6, citing `witness_state.py:198–203` |
| Transaction, header, access list, BAL | **not yet specified** (`EthBlock`, `EthStateless` are empty) | — |

So by construction leanerSTFSpec sits with execution-specs on every evm-sail
divergence it can express: W1–W5 and W10–W18 directly, and W6–W9 at the
field-adapter level. It goes further than an executable copy. It *proves*
the exact accepting set of the account-leaf decoder
(`decodeAccountLeaf_eq_ok_iff`, line 263), so its acceptance of leading zeros,
`0xc0` defaults and unbounded nonces is a stated theorem, not an accident of
the implementation.

### 6.2 What the transaction column means

leanerSTFSpec has no transaction decoder yet. For `compare_transaction.py`,
`leaner/LeanerDecode.lean` composes the spec's own typed RLP adapters against
the EELS `FeeMarketTransaction` field schema (chain_id `U64`, nonce `U256`,
fees and gas `Uint`, `to` as `union2 (toFixed 0) (toFixed 20)`, value and
signature `U256`). That schema is the one leanerSTFSpec's informal `EthBlock`
spec (R-TX) requires. The column shows that the adapters reject W6–W9 the way
execution-specs does. It is not a test of a leanerSTFSpec transaction decoder,
because none exists yet. When `EthBlock` lands, this column should switch to
calling it.

### 6.3 New witnesses from reading leanerSTFSpec

leanerSTFSpec's SC5/SC6 contracts list the lenient cases explicitly: `[]` as a
falsy default, an unbounded nonce, a numerical (not byte-count) balance bound,
and list-valued storage leaves read as 0. Each of these is a place to probe
evm-sail. Every one is a divergence (W10–W18), all in the "evm-sail stricter"
direction.

### 6.4 Results

| Script | Cases | specs vs evm-sail | specs vs leaner | evm-sail vs leaner |
| --- | --- | --- | --- | --- |
| `compare_account_leaf.py` | 15 | 9 | **0** | 9 |
| `compare_transaction.py` | 5 | 4 | **0** | 4 |
| `compare_storage_leaf.py` | 10 | 5 | **0** | 5 |

"Agree" means both reject, or both accept with identical decoded values.
Rejection reasons are not compared.

## 7. Files

| File | Contents |
| --- | --- |
| `RLP-SCALAR-DIVERGENCE.md` | This document |
| `compare_account_leaf.py` | Witnesses W1–W5, W10–W13 plus agreeing controls |
| `compare_transaction.py` | Witnesses W6–W9 plus the baseline |
| `compare_storage_leaf.py` | Witnesses W14–W18 plus agreeing controls |
| `report.py` | Three-way agreement printing shared by the scripts |
| `evm_sail_path.py` | Locates the evm-sail extraction |
| `leaner_stf.py`, `leaner/LeanerDecode.lean` | Locates leanerSTFSpec and runs the Lean driver |
| `output-*.txt` | Saved runs |

# evm-sail vs execution-specs vs leanerSTFSpec: RLP scalar strictness

A differential test of how three specifications of the stateless guest decode
RLP-encoded numbers and fixed-width byte fields:
[evm-sail](https://github.com/frisitano/evm-sail),
[execution-specs](https://github.com/ethereum/execution-specs) and
[leanerSTFSpec](https://github.com/alexanderlhicks/leanerSTFSpec). The test
covers where each one accepts or rejects leading zero bytes, non-minimal
framing, empty-list fields, and wrong-length hashes and addresses.

**leanerSTFSpec agrees with execution-specs on every case, decoded values
included; evm-sail disagrees with both, in both directions.** Eighteen
concrete encodings are given, each executed against all three:

- Twelve that execution-specs and leanerSTFSpec **accept** and evm-sail
  **rejects**:
  - account trie leaves whose `nonce` or `balance` carries a leading zero
    byte, is written as the empty list, or is wider than evm-sail's types
    allow;
  - storage leaves with leading zeros, or written as a list.
- Six that evm-sail **accepts** and execution-specs and leanerSTFSpec
  **reject**:
  - short hashes and addresses, which evm-sail silently zero-extends;
  - a non-canonical `y_parity`;
  - a 21-byte `to` field whose leading byte evm-sail silently discards.

leanerSTFSpec has no transaction decoder yet. Its transaction column composes
the spec's typed RLP field adapters against the EELS transaction schema (see
§6.2 of the write-up).

**[→ Full write-up, with the witness bytes and source references](RLP-SCALAR-DIVERGENCE.md)**

## Running it

```bash
git clone https://github.com/frisitano/evm-sail.git
git -C evm-sail checkout adc44afd21ef6d5a45c96046f0d23f527acbf54e
git clone https://github.com/ethereum/execution-specs.git
git -C execution-specs fetch origin e1a316a06fc3d3e0a5da36fdc78580811e9d8a36
git -C execution-specs checkout e1a316a06fc3d3e0a5da36fdc78580811e9d8a36
git clone https://github.com/alexanderlhicks/leanerSTFSpec.git
git -C leanerSTFSpec checkout daa6a8a4e13e3ce9e54c3b4da6f60dac7ac42de0
(cd leanerSTFSpec && lake build EthStateCommit EthCodec)   # needs elan

# Python 3.12: execution-specs pulls in coincurve, which has no wheel for 3.14
# and fails to build there.
python3.12 -m venv venv
venv/bin/pip install -e ./execution-specs pydantic ethereum-rlp==0.1.6

venv/bin/python compare_account_leaf.py
venv/bin/python compare_transaction.py
venv/bin/python compare_storage_leaf.py
```

execution-specs is pinned at `tests-zkevm@v21.0.0`, the normative target
leanerSTFSpec pins. evm-sail's side is its checked-in Python extraction, so no
Sail build is needed. leanerSTFSpec's side is `leaner/LeanerDecode.lean`,
interpreted with `lake env lean --run` inside the built checkout. Each script
looks for a checkout first in `$EVM_SAIL` / `$LEANER_STF_SPEC`, then inside
this repo, then beside it.

Saved output from the pinned revisions is in `output-*.txt`.

## Contents

| File | Contents |
| --- | --- |
| `RLP-SCALAR-DIVERGENCE.md` | The write-up: rule sets, site-by-site table, witnesses, analysis |
| `compare_account_leaf.py` | Account trie leaf — witnesses W1–W5, W10–W13 and agreeing controls |
| `compare_transaction.py` | Type-2 transaction — witnesses W6–W9 and the baseline |
| `compare_storage_leaf.py` | Storage trie leaf — witnesses W14–W18 and agreeing controls |
| `report.py` | Three-way agreement printing |
| `evm_sail_path.py` | Locates the evm-sail extraction |
| `leaner_stf.py`, `leaner/LeanerDecode.lean` | Locates leanerSTFSpec and runs the Lean driver |
| `output-*.txt` | Saved runs |

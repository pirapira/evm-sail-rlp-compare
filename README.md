# evm-sail vs execution-specs: RLP scalar strictness

A differential test of how [evm-sail](https://github.com/frisitano/evm-sail) and
[execution-specs](https://github.com/ethereum/execution-specs) decode
RLP-encoded numbers and fixed-width byte fields — specifically, where each one
accepts or rejects leading zero bytes, non-minimal framing, and wrong-length
hashes and addresses.

**They disagree, in both directions.** Nine concrete encodings are given, each
executed against both implementations:

- Three that execution-specs **accepts** and evm-sail **rejects** — account trie
  leaves whose `nonce` or `balance` carries a leading zero byte.
- Six that evm-sail **accepts** and execution-specs **rejects** — short hashes
  and addresses (silently zero-extended), a non-canonical `y_parity`, and a
  21-byte `to` field whose leading byte evm-sail silently discards.

**[→ Full write-up, with the witness bytes and source references](RLP-SCALAR-DIVERGENCE.md)**

## Running it

```bash
git clone https://github.com/frisitano/evm-sail.git
git -C evm-sail checkout 45fc3fce902fe4853e9d53bfafe2446ed5ab51aa
git clone https://github.com/ethereum/execution-specs.git
git -C execution-specs checkout e5a8caf1b8055e4d805c7fb169edfa710914b7da

# Python 3.12: execution-specs pulls in coincurve, which has no wheel for 3.14
# and fails to build there.
python3.12 -m venv venv
venv/bin/pip install -e ./execution-specs pydantic

venv/bin/python compare_account_leaf.py
venv/bin/python compare_transaction.py
```

evm-sail's side is its checked-in Python extraction, so no Sail build is
needed. The scripts look for the checkout at `./evm-sail`, then `../evm-sail`,
then `$EVM_SAIL`.

Saved output from the pinned revisions is in `output-account-leaf.txt` and
`output-transaction.txt`.

## Contents

| File | Contents |
| --- | --- |
| `RLP-SCALAR-DIVERGENCE.md` | The write-up: rule sets, site-by-site table, witnesses, analysis |
| `compare_account_leaf.py` | Account trie leaf — witnesses W1–W5 and agreeing controls |
| `compare_transaction.py` | Type-2 transaction — witnesses W6–W9 and the baseline |
| `evm_sail_path.py` | Locates the evm-sail extraction |
| `output-*.txt` | Saved runs |

/-
Driver for the leanerSTFSpec column of the differential test.

Reads one case per line on stdin, `<kind> <hex>`, and prints one result line per
case: `ACCEPT ...` or `REJECT <reason>`.  Kinds:

  account  STFSpec.StateCommit.decodeAccountLeaf HashConsts.literals
  storage  STFSpec.StateCommit.decodeStorageLeaf
  tx       a type-2 transaction, decoded with the typed RLP adapters of
           STFSpec.Codec.Rlp against the EELS `FeeMarketTransaction` schema.
           leanerSTFSpec has no transaction decoder yet (EthBlock is
           scaffolding only), so this composes the field adapters it does
           have; it is not a decoder the spec itself defines.

Run from a built leanerSTFSpec checkout:

  lake env lean --run /path/to/LeanerDecode.lean < cases.txt
-/
import STFSpec.StateCommit.AccountDecode
import STFSpec.StateCommit.StorageDecode
import STFSpec.Codec.RlpTyped

open STFSpec STFSpec.Base STFSpec.Codec STFSpec.State STFSpec.StateCommit

def hexDigit? (c : Char) : Option Nat :=
  if '0' ≤ c ∧ c ≤ '9' then some (c.toNat - '0'.toNat)
  else if 'a' ≤ c ∧ c ≤ 'f' then some (c.toNat - 'a'.toNat + 10)
  else if 'A' ≤ c ∧ c ≤ 'F' then some (c.toNat - 'A'.toNat + 10)
  else none

def parseHex (s : String) : Option ByteArray := do
  let cs := s.toList
  if cs.length % 2 ≠ 0 then none
  let rec go : List Char → ByteArray → Option ByteArray
    | [], acc => some acc
    | hi :: lo :: rest, acc => do
      let h ← hexDigit? hi
      let l ← hexDigit? lo
      go rest (acc.push (UInt8.ofNat (16 * h + l)))
    | [_], _ => none
  go cs ByteArray.empty

/-- Lower-case hex of `n`, zero-padded to `width` bytes. -/
def hexOf (n width : Nat) : String :=
  let digits := String.ofList (Nat.toDigits 16 n)
  String.ofList (List.replicate (2 * width - digits.length) '0') ++ digits

def hexBytes (b : ByteArray) : String :=
  String.join (b.toList.map fun x ↦ hexOf x.toNat 1)

def witnessError : WitnessError → String
  | .missing _ => "missing"
  | .malformed .leaf => "malformed(leaf)"
  | .malformed _ => "malformed"
  | .unresolved _ => "unresolved"

def rlpError : RlpError → String
  | .empty => "empty"
  | .truncated => "truncated"
  | .trailing => "trailing"
  | .nonCanonical why => s!"nonCanonical({why})"
  | .shape ctx => s!"shape({ctx})"

def runAccount (leaf : ByteArray) : String :=
  match decodeAccountLeaf HashConsts.literals leaf with
  | .ok (acc, root) =>
    s!"ACCEPT nonce={acc.nonce} balance={acc.balance.toNat} " ++
    s!"storage_root={hexOf root.toNat 32} code_hash={hexOf acc.codeHash.toNat 32}"
  | .error e => s!"REJECT {witnessError e}"

def runStorage (leaf : ByteArray) : String :=
  match decodeStorageLeaf leaf with
  | .ok v => s!"ACCEPT value={v.toNat}"
  | .error e => s!"REJECT {witnessError e}"

/-- Field adapters in EELS `FeeMarketTransaction` order: chain_id U64, nonce U256,
two fee Uints, gas Uint, to `Bytes0 | Address`, value U256, data Bytes,
access_list tuple, y_parity / r / s U256. -/
def decodeFeeMarket (payload : ByteArray) : Except RlpError (Nat × ByteArray) := do
  let item ← Rlp.decode payload
  let fs ← Rlp.toFields 12 item
  let _ ← Rlp.toNatBounded 8 fs[0]
  let _ ← Rlp.toNatBounded 32 fs[1]
  let _ ← Rlp.toNat fs[2]
  let _ ← Rlp.toNat fs[3]
  let _ ← Rlp.toNat fs[4]
  let toBytes ← Rlp.union2
    (fun x ↦ (Rlp.toFixed 0 x).map (fun v ↦ v.toBytes.toByteArray))
    (fun x ↦ (Rlp.toFixed 20 x).map (fun v ↦ v.toBytes.toByteArray)) fs[5]
  let _ ← Rlp.toNatBounded 32 fs[6]
  let _ ← Rlp.toBytes fs[7]
  let _ ← Rlp.toList fs[8]
  let yParity ← Rlp.toNatBounded 32 fs[9]
  let _ ← Rlp.toNatBounded 32 fs[10]
  let _ ← Rlp.toNatBounded 32 fs[11]
  return (yParity, toBytes)

def runTx (tx : ByteArray) : String :=
  if tx[0]? ≠ some 2 then "REJECT not a type-2 transaction" else
  match decodeFeeMarket (tx.extract 1 tx.size) with
  | .ok (y, to) => s!"ACCEPT y_parity={y} to=0x{hexBytes to}"
  | .error e => s!"REJECT {rlpError e}"

def runLine (line : String) : String :=
  match line.trimAscii.toString.splitOn " " with
  | [kind, hex] =>
    match parseHex hex with
    | none => "ERROR bad hex"
    | some b =>
      match kind with
      | "account" => runAccount b
      | "storage" => runStorage b
      | "tx" => runTx b
      | _ => s!"ERROR unknown kind {kind}"
  | _ => "ERROR expected `<kind> <hex>`"

partial def loop (stdin : IO.FS.Stream) (stdout : IO.FS.Stream) : IO Unit := do
  let line ← stdin.getLine
  if line.isEmpty then return
  if line.trimAscii.isEmpty then loop stdin stdout else
  stdout.putStrLn (runLine line)
  stdout.flush
  loop stdin stdout

def main : IO Unit := do
  loop (← IO.getStdin) (← IO.getStdout)

# The Bitcoin Block Priority Oracle — Explained

## The Problem (Story)

Every 10 minutes, Bitcoin produces a block. ~4 million weight units. That's the whole settlement layer for the global economy.

Inside that block, two completely different markets compete for space:

- A Lightning channel close that will lose money every second it waits
- A BRC-20 mint that's worth the same next block, next hour, or next Tuesday
- A DEX settlement that needs to settle before the market moves
- An Ordinal inscription of a pixelated cat

The market treats them identically. Highest fee-rate wins.

A settlement that is worth *nothing* if it misses this block competes with an inscription that would be perfectly fine waiting. The market can't tell the difference because both transactions look the same — they're just inputs, outputs, and signatures.

**This is not a bug in Bitcoin. It's a missing signal in the fee market.**

---

## What We Tried First (v1)

The initial idea was simple: let the wallet declare its intent. Add 4 bytes to the transaction — an OP_RETURN with a flag: 0 for financial, 1 for data. The pool reads this and allocates block space with a minimum 30% floor for financial transactions.

```c
OP_RETURN 0x7072 0x01 0x00
// Magic  Ver   Tag (0=financial, 1=data)
```

4 bytes. No fork. No consensus change. Elegant.

We posted this on Reddit. The response was sharp and mostly correct:

> *"What stops spammers from declaring their data as 'financial'?"*

They were right. A lying wallet costs nothing. The declaration is just bytes — anyone can write whatever they want. The v1 design trusted the wallet to be honest, and that's not how Bitcoin works.

---

## What We Learned (v2)

The key insight that v1 missed: **you don't need to trust the wallet. You just need to verify after the fact.**

A transaction that declares "financial" but has a 400KB witness with an ordinal envelope is *structurally* a data transaction. The pool can detect this at template assembly time — cheaply, deterministically, and without any cryptographic tricks.

**v2 fixes the liar problem with a structural backcheck:**

| Check | What it detects | Cost |
|-------|----------------|------|
| Witness ratio | `witness_size / vsize > 0.3` → data-like | O(1) |
| Ordinal envelope | `0x00 0x63 "ord" ... 0x68` in witness → DATA | O(witness size) |
| Runestone marker | `0x6a 0x5d` in outputs (block ≥ 840K) → DATA | O(output count) |
| Inscriber history | Input from known inscriber address → DATA | O(1) lookup |

**Why this changes the game:** A liar gets reclassified at template assembly time — the same outcome as telling the truth. The incentive flips from "can I lie and get priority?" to "why would I bother lying if I get the same result?"

The second v1 problem was the fixed 25% data premium. A hardcoded premium doesn't adapt to market conditions. During quiet periods it's unnecessary. During congestion it might be too low or too high.

**v2 replaces the fixed premium with a blind batch auction:**

```
Step 1: Fill financial floor (min 30% of block)
Step 2: Fill remaining space with the highest-fee tx from either pool
Step 3: Data premium = fee of marginal data tx − fee of marginal financial tx
```

The premium emerges from mempool pressure. Zero during quiet periods. Equilibrium during congestion. The pool doesn't set the price — the market does.

---

## The Technical Architecture

### Layer 1: Wallet Declaration

A 4-byte OP_RETURN in the first output of the transaction:

```
OP_RETURN 0x7072 0x01 0x00
          magic  ver   flags
```

- `0x7072` = "pr" (priority magic)
- `0x01` = protocol version
- Flags bit 0: 0 = financial, 1 = data

Taproot wallets can use the witness annex instead — zero additional vBytes (annex is witness data, 4 WU = 1 vB).

Overhead: ~10 vB with the OP_RETURN output. Gets pruned from UTXO set. No long-term blockchain bloat.

### Layer 2: Pool Template Assembly

The pool runs two ordered pools at template assembly time:

1. **Financial pool** — Transactions tagged (or verified) as FINANCIAL, sorted by fee-rate descending
2. **Data pool** — Transactions tagged as DATA, sorted by fee-rate descending

**Allocation algorithm:**
1. Fill financial floor: `min_financial = min(block_capacity × 0.30, total_financial_weight)`
2. Fill remaining space with the highest-fee transaction from either pool
3. The marginal data premium emerges naturally from the fee gap between the two pools

### Layer 3: Anti-Abuse

The structural backcheck runs on every declared-"financial" transaction before template assembly:

- **Witness ratio check:** If `witness_size / virtual_size > 0.3`, the transaction is likely data-heavy. Reclassify.
- **Ordinal envelope scan:** Look for the `OP_FALSE OP_IF "ord"...OP_ENDIF` pattern in witness tapscripts. This is the definitive signal for Ordinal inscriptions.
- **Runestone detection:** Scan outputs for `OP_RETURN OP_13` (0x6a 0x5d) — the runestone protocol marker. Only applies at block heights ≥ 840,000.
- **Inscriber bloom filter:** Optional — pools can share a lightweight bloom filter of addresses with a history of false declarations. No central database, no privacy loss.

### Layer 4: Fee Estimator API (works today, zero pool adoption needed)

The fee estimator monitors the mempool, classifies transactions using the same structural heuristics, and publishes separate fee estimates:

```
GET /v1/fees

{
  "financial": { "fastest": 120, "hour": 45 },
  "data": { "fastest": 200, "hour": 80 },
  "mempool": { "financial_vsize_mb": 52, "data_vsize_mb": 33 }
}
```

Wallets call this endpoint. For financial payments, use `financial.fastest`. For inscriptions, use `data.fastest`. **This works before any pool adopts the oracle** — it's just better information for the market.

---

## How It Compares to Alternatives

| Approach | Consensus change? | Trust required? | Works today? | Handles liars? |
|----------|------------------|----------------|-------------|----------------|
| **Priority Oracle (v2)** | No | No | Yes (estimator) | Structural backcheck |
| CPFP/RBF | No | No | Yes | N/A (doesn't classify) |
| Pool-side classifier | No | Yes (trust pool) | Yes | Centralized oracle |
| BIP-110 (ban inscriptions) | Yes (soft fork) | No | No | Would ban all data |
| Block size increase | Yes (hard fork) | No | No | Political deadlock |

---

## Future Upgrades

### Short-term (months)

**Wallet SDKs** — Rust, JavaScript, Swift, Kotlin libraries that add the 4-byte declaration to outgoing transactions. The wallet doesn't need to change UX — just add the OP_RETURN automatically.

**Pool adapter** — Open-source template assembly hook that any Stratum v1 or v2 pool can deploy. Configuration-driven: set the financial floor percentage, enable/disable the structural backcheck, configure the bloom filter.

**Cross-pool reputation** — A distributed bloom filter shared between participating pools. Wallets that repeatedly false-declare get flagged across the network. No central coordinator, no private data leaked.

### Medium-term (year)

**Bonded declarations** — Wallets can optionally stake a small amount of BTC that gets slashed if the declaration is proven false. This turns the heuristic backcheck into an economic backstop. Inspired by optimistic rollup fraud proofs.

**Multi-tier classification** — Beyond binary financial/data, introduce tiered classes: `0x00` (financial), `0x01` (data), `0x02` (high-priority financial — for time-sensitive settlements), `0x03` (low-priority data — for archival inscriptions). Each tier gets a different floor allocation.

**Stratum v2 native messages** — If Stratum v2 achieves meaningful adoption, the oracle's classification tags can be embedded as native Template Distribution Protocol messages: `SetClassificationRules`, `ClassifiedTemplate`, `PriorityPreference`.

### Long-term (years)

**Consensus-level priority signaling** — If the community decides that transaction classes should be a first-class concept, the 4-byte OP_RETURN format could evolve into a BIP. This would make the declaration mandatory and verifiable by full nodes, not just pools. This is a much longer conversation — but the oracle gives us real-world data on whether the classification is useful before we enshrine it in consensus.

**Programmatic fee markets** — Wallets could declare not just the class but the *maximum acceptable delay*: "I need this within 3 blocks" or "I can wait 24 hours." Pools optimize block production against these time constraints instead of just fee rates. This turns the fee market into a *scheduling market*.

---

## Summary

The Bitcoin Block Priority Oracle is not a consensus change. It's not cryptographic enforcement. It's a 4-byte signal with a structural backstop, an adaptive pricing model, and a gradual rollout that delivers value at every stage:

- **Today:** The fee estimator API gives wallets better information, even if zero pools adopt.
- **Tomorrow:** Pools deploy the template assembly hook. Financial transactions get a transparent priority lane during congestion.
- **Next year:** Bonded declarations, multi-tier classification, cross-pool reputation.
- **Long-term:** The data we collect tells us whether priority signaling should become a first-class Bitcoin feature.

No fork. No magic. Just 4 bytes of honesty with a backstop.

---

*Built with coffee and a lot of staring at mempool.space*

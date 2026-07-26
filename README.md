# Bitcoin State Pricing Research

**Status: Open Research — Not a Solution**

We thought we had a solution to Bitcoin's data inscription problem. We were wrong. Twice.

This repo documents our journey from attempted solution → failed idea → honest research.

## What Happened

1. **v1: Priority Classification Oracle** — 4-byte OP_RETURN flag to classify transactions as financial/data. Miners allocate block space with a floor for financial transactions. Dead. Incentive misalignment: miners won't leave fees on the table.

2. **v2: Externality Fee** — Structural backcheck + formula-based fee to price the "true cost" of data transactions. Dead. Any formula is an arbitrary tax, not a market price.

3. **v3: Open Research** — We identified the real problem: Bitcoin has no mechanism to price permanent storage cost in its UTXO set. Nobody has solved this. We're researching what exists and framing the open questions.

## What's Here

| File | Description |
|------|-------------|
| `bitcoin-oracle-arch.md` | v3 architecture document — surveys existing research, references BIPs and papers, frames open problems |
| `bitcoin-oracle-explained.md` | Original v1/v2 proposal (kept for reference) |
| `interactive-block.html` | Interactive block visualization with v3 research framing |

## The Real Problem

Bitcoin's UTXO set has grown from ~40M entries (2017) to ~150M+ (2026). Every unspent output must be kept in RAM by every full node, forever. The cost is distributed across all node operators — not paid by the transaction creator. The fee market only prices block space (supply ≈ 4 MWU per block), not state storage.

**This is a market failure, and no one has solved it.**

## Key References

- **BIP-141 (SegWit):** The only existing differential pricing mechanism. Witness data costs 1/4 of base data. Arbitrary 4× discount was designed for malleability fix, not state pricing.
- **State expiry:** Discussed on bitcoin-dev since ~2020 by Rusty Russell, Gregory Maxwell, et al. No BIP. No consensus.
- **Covenants (BIP-119, OP_VAULT, OP_TX, OP_CAT):** Could reduce UTXO churn through stateful constructions. Active research.
- **Paper: "Enhancing Bitcoin Transactions with Covenants" (FC'17)** — Formalizes covenant constructions.

## How This Repo Is Organized

This is a sub-project within the [TELOS Cognitive Operating System](telos/README.md) monorepo. TELOS is a 20-axiom CogOS at `/telos/`. The Bitcoin research lives at the root level.

## License

Research use. See CONTRIBUTING.md for details.

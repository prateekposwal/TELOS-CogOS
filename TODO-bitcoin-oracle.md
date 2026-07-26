# Bitcoin State Pricing Research — Task List

## Status: Complete Pivot to v3 (Open Research)

After extensive Reddit feedback:
- **v1 (Priority Classification Oracle)** → Dead. Incentive misalignment. Miners won't leave fees on the table.
- **v2 (Externality Fee)** → Dead. Any formula-based fee is an arbitrary tax, not a market price.
- **v3 (Open Research)** → Current. We identified a real problem: Bitcoin has no mechanism to price permanent state storage. We don't have a solution. We're researching what exists and framing the open questions.

---

## 📋 Phase R1: Survey Existing Work

- [x] Document SegWit discount (BIP-141) and its unintended consequences for data pricing
- [x] Survey state expiry discussions on bitcoin-dev (Rusty Russell, Gregory Maxwell, et al.)
- [x] Catalog covenant proposals relevant to state management (BIP-119, OP_VAULT, OP_TX, OP_CAT)
- [x] Map UTXO growth data and trends (~40M in 2017 → ~150M+ in 2026)
- [x] Write v3 architecture document (`bitcoin-oracle-arch.md`)
- [ ] Publish survey as a public resource

## 📋 Phase R2: Formalize the Problem

- [ ] Define the UTXO cost function (what are the real costs to node operators?)
- [ ] Analyze SegWit discount as a pricing mechanism (what was its actual effect on data?)
- [ ] Model the externality of data inscriptions on node operators
- [ ] Compare with other UTXO-based chains (Ethereum, Cardano, Litecoin)
- [ ] Write a formal problem statement for bitcoin-dev mailing list

## 📋 Phase R3: Propose Research Directions

- [ ] Draft a UTXO fee market framing (not a solution — a framing)
- [ ] Evaluate state expiry tradeoffs in a formal analysis (hard questions: reclaiming, timelocks, hardware wallets)
- [ ] Design a block weight refactoring that accounts for UTXO cost
- [ ] Submit to bitcoin-dev mailing list for discussion
- [ ] Present at a Bitcoin conference or meetup

## 📋 Phase R4: Build Simulation (If Useful)

- [ ] Simulate UTXO set growth under different fee models
- [ ] Model node operator costs under different scenarios
- [ ] Publish reproducible results

---

## 📣 Content (Paused — Need Honest Framing)

The LinkedIn content series is paused until we have something worth saying. Posting about a failed oracle design would generate interest but not value. When we have meaningful research results, we'll publish:

| # | Title | Status |
|---|-------|--------|
| 1 | "Bitcoin can't price its own memory — and that's the interesting problem" | Idea |
| 2 | "State expiry has been discussed for 6 years. Here's why there's no BIP." | Idea |
| 3 | "What we learned from failing publicly on Reddit" | Idea |

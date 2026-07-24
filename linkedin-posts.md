# LinkedIn Post Series — Bitcoin Block Priority Oracle

---

## Post 1: The Problem (Architecture / Big Picture)

**Headline:** Bitcoin blocks aren't full. They're contested.

**Body:**

Every Bitcoin block has exactly 4 million weight units. Today, two completely different markets compete for that space:

1. **Financial transactions** — payments, settlements, Lightning channel opens, DEX swaps
2. **Data inscriptions** — Ordinals, BRC-20, Runes

The market treats them identically. Highest fee-rate wins.

But they have fundamentally different time-value curves:
- A settlement is worth nothing if it misses this block
- An inscription is worth the same next block, or next hour

Bitcoin's block space is a shared resource with no priority lanes. The result? Financial transactions get priced out during inscription mania, and data transactions fill blocks during low-fee periods — both inefficient.

We can fix this without a soft fork, without a hard fork, without any consensus change.

**The idea:** A lightweight oracle that classifies transactions as "financial" or "data" before block template assembly, enabling a two-tier priority fee market. Miners opt in voluntarily, keep full discretion, and attract financial transaction fee flow that currently goes elsewhere.

I'm building the architecture. Thread below ↓

#Bitcoin #Ordinals #Layer2 #Mining #StratumV2

---

## Post 2: The Architecture (Technical / Dev Audience)

**Headline:** How to build a transaction classifier without touching consensus

**Body:**

The Bitcoin Block Priority Oracle sits between the mempool and the Stratum v2 template builder. It has three components:

**1. Transaction Classifier (Rust)**

Pattern-matches against:
- Witness data / input ratio → flag data-heavy tx
- Taproot script path spends with large witnesses → Ordinal inscriptions
- Standard P2PKH/P2WPKH → financial
- HTLCs, multisig, timelocks → financial

Each tx gets a tag: FINANCIAL | DATA | UNCERTAIN. False positives default to financial.

**2. Priority Fee Market**

Two virtual pools, one allocation algorithm:

- Financial txes get minimum 30% block space reservation
- Remaining 70% split proportional to fee ratio between the two pools
- Result: financial txes are never fully crowded out

**3. Stratum v2 Plugin**

Three new messages over the Template Distribution Protocol:
- `SetClassificationRules` — pool publishes its classification logic
- `ClassifiedTemplate` — template with per-tx tags
- `PriorityPreference` — miner signals their desired allocation (default: 30% financial floor)

Full architecture doc in the repo. Link below.

No consensus change. No miner lock-in. Just a smarter template.

#BitcoinDev #Rust #StratumV2 #MiningInfrastructure

---

## Post 3: The Why / Call to Action (Industry / Mining Audience)

**Headline:** Why every mining pool should run a transaction oracle

**Body:**

Miners optimize for fee revenue. Here's the blind spot:

Financial transactions have alternatives — they can go to Liquid, Lightning, or sidechains. If Bitcoin blocks consistently favor data inscriptions, financial tx volume migrates elsewhere.

Data inscriptions have no alternatives — they exist because of Bitcoin's security budget and permanence.

This creates a long-term risk: if financial tx fee flow leaves Bitcoin, the security budget becomes dependent on inscription mania cycles.

A priority oracle solves this:

- **For miners:** Attract sticky financial tx fee flow. Differentiate your pool. Offer priority confirmation SLAs to exchanges and payment processors.
- **For users:** Predictable confirmation times for payments. Separate fee market from the inscription frenzy.
- **For Bitcoin:** Healthy fee market with natural price discovery, not feast-or-famine cycles.

I'm open-sourcing the architecture and looking for:
- A pool operator to prototype with
- Rust devs interested in Bitcoin protocol work
- A Stratum v2 implementation to integrate with

Full architecture: [link to repo/arch doc]

What do you think? Would you run a priority oracle at your pool?

#BitcoinMining #MiningPool #BTC #BitcoinInfrastructure

---

## Bonus Ideas (future posts)

### Post 4: Deep dive — the allocation algorithm
Walk through the math of the financial/data split. Show how it responds to different fee regimes. Interactive visualization.

### Post 5: Trust model and decentralization roadmap
Phase 1: pool-operated, open-source classifier. Phase 2: multi-oracle with median selection. Phase 3: succinct classification proofs.

### Post 6: Performance benchmarks
Template generation time, classification throughput, comparison with vanilla template builder.

### Post 7: Why not MEV-Boost for Bitcoin?
Compare with Ethereum's PBS model. Why a classification oracle is simpler and more appropriate for Bitcoin's security model.

### Post 8: Wallet integration
Show how a wallet queries the fee estimator API and displays separate fee suggestions for financial vs. inscription transactions.

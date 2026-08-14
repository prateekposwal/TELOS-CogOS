# Bitcoin State Pricing Oracle — Research Direction (v3)

## Status: Honest Assessment

This document supersedes the v1 (priority classification) and v2 (externality fee) proposals. Both were refuted on Reddit for fundamental economic reasons:

- **v1 died** because miners won't leave fees on the table. A voluntary classification system with no economic penalty for lying collapses to zero signal.
- **v2 died** because any formula-based "externality fee" is an arbitrary tax, not a market price. Without a mechanism that produces a price (supply + demand for a specific good), you cannot price the cost of a transaction.

Both failures share a root cause: **Bitcoin has no mechanism to price the permanent storage cost of data in its UTXO set.** This document surveys what actually exists, what people are working on, and where the real open problems are.

---

## The Real Problem: Unpriced State Growth

Bitcoin's UTXO set has grown from approximately 40 million entries in 2017 to over 150 million in 2026. Every unspent transaction output must be kept in RAM by every full node, forever. The cost of this storage is:

- **Distributed across all node operators** — not paid by the transaction creator
- **Non-degradable** — a UTXO created in 2012 costs the same to store today as one created last week
- **Non-excludable** — you cannot refuse to validate a block because it uses too many UTXOs

The SegWit discount (BIP-141) made this worse by effectively pricing witness data at 25% of base data. Since inscriptions store their content in the witness, they get a 4× discount versus on-chain data while imposing the same UTXO set burden.

---

## What Already Exists

### 1. BIP-141: Segregated Witness (SegWit) — The Only Existing Pricing Mechanism

- **Status:** Deployed (2017)
- **What it did:** Created the weight unit system: `block_weight = base_size × 3 + total_size × 1`
- **Effect:** Witness data costs 1/4 of base data per byte
- **Relevance:** This is the *only* mechanism Bitcoin has for differential data pricing. It was designed to fix transaction malleability, not to price state storage. The 4× discount was arbitrary.
- **Link:** [BIP-141](https://github.com/bitcoin/bips/blob/master/bip-0141.mediawiki)

### 2. UTXO Growth — Known But Unaddressed

The UTXO set growth problem has been discussed extensively but no consensus change has been deployed to address it.

**Key data points:**
- UTXO set size: ~40M (2017) → ~80M (2021) → ~150M+ (2026)
- Inscriptions (Ordinals, BRC-20) have accelerated growth since 2023
- Each new UTXO costs ~50 bytes minimum + node RAM cost + index overhead
- Full node RAM requirement for UTXO cache: ~5-10 GB and growing

### 3. State Expiry Discussions (No BIP, No Consensus)

Several proposals have been discussed but none have reached BIP status:

- **UTXO expiry with renewal fees** — UTXOs expire after N blocks unless renewed with a fee
- **Rent on UTXOs** — Periodic fee for UTXO set inclusion
- **Inactivity pruning** — UTXOs unspent for N years become spendable by miners
- **State commitment batching** — Merkle-commit to UTXO set rather than storing individually

**Who's discussed it:**
- Rusty Russell (Bitcoin Core contributor) — proposed state expiry concepts on bitcoin-dev
- Gregory Maxwell — discussed UTXO growth costs and potential solutions
- Anthony Towns — explored covenant-based approaches to state management

### 4. Covenant Proposals (Indirectly Relevant)

Covenants allow a script to constrain future spending. Relevant covenant proposals:

| Proposal | Status | Relevance |
|----------|--------|-----------|
| **BIP-119: OP_CHECKTEMPLATEVERIFY** | Draft | Enables output-constrained spending |
| **OP_VAULT** | Draft | Enables vault constructions with recovery |
| **OP_TX / OP_TXHASH** | Draft | Generic transaction introspection |
| **OP_CAT (BIP-347)** | Draft | Concatenation enabling covenant construction |
| **OP_CHECKSIGFROMSTACK** | Discussion | Signature verification from stack |

**Why covenants matter for state pricing:** A covenant can enforce that a UTXO must be spent in a particular way. This enables constructions like "stateful channels" where UTXOs are reused rather than created and destroyed, reducing UTXO set churn. They are a tool, not a solution.

**Links:**
- [BIP-119 (OP_CTV)](https://github.com/bitcoin/bips/blob/master/bip-0119.mediawiki)
- [Covenants topic on Bitcoin Optech](https://bitcoinops.org/en/topics/covenants/)
- [Covenants research paper (FC'17)](https://fc17.ifca.ai/bitcoin/papers/bitcoin17-final28.pdf)

### 5. SegWit Discount — Unintended Consequences

The SegWit 4× witness discount was designed to:
- Fix transaction malleability
- Increase block capacity
- Enable second-layer protocols (Lightning)

It was not designed to price witness data for storage cost. The result is that data-heavy transactions (inscriptions) get a 4× discount on block space while imposing the same UTXO set burden. This is a known issue but fixing it would require a hard fork.

---

## The Open Research Questions

There is no working solution to pricing state growth in Bitcoin. These are the actual open problems:

### Q1: How do you price permanent state addition without a market?

In a permissionless system, you cannot charge "rent" — there's no entity to collect it and no way to enforce payment. UTXO expiry has been discussed but raises hard questions:
- Who reclaims expired UTXOs?
- What happens to time-locked contracts?
- How do hardware wallets verify expiry?

### Q2: Can block weight be refactored to account for UTXO cost?

The SegWit weight formula (base×3 + witness×1) was a first attempt at differential pricing. Could we design a weight formula that accounts for UTXO set impact?
- `new_weight = base_bytes × w_base + witness_bytes × w_witness + new_utxos × w_utxo_count + data_bytes × w_data`

This is an arbitrary formula (as the Reddit thread correctly identified). What economic mechanism produces the weights?

### Q3: What is the "true cost" of a UTXO entry?

A UTXO costs:
- ~50-100 bytes in the UTXO set
- ~32 bytes in the hash set
- ~5-10 GB RAM for the whole set
- Validation time per block
- Disk I/O for node catch-up

None of these costs are priced in the fee market. The fee market only prices block space (supply ≈ 4 MWU per block, demand = competing fees). UTXO set storage is a commons.

### Q4: Can layer-2 absorb the state growth?

Lightning Network and other L2 protocols reduce on-chain state by keeping transactions off-chain. But:
- L2 requires channel factories (more UTXOs)
- Inscriptions bypass L2 entirely
- L2 adoption is insufficient to offset inscription growth

### Q5: Do we need a UTXO fee market?

Proposed direction: a second fee market for UTXO creation.
- Transactions pay a fee proportional to the number of new UTXOs they create
- The fee is burned (like existing fees) — no entity collects it
- The fee rate adjusts based on UTXO set growth rate
- This is NOT a price — it's a congestion signal

**Problem:** This is still an arbitrary formula. Who sets the rate? How does it adapt?

---

## Research Direction (Not a Solution)

This project pivots from "building an oracle" to **researching the open problem of state cost pricing in Bitcoin.** The deliverables change accordingly:

### Phase R1: Survey Existing Work (Complete)
- [x] Document SegWit discount and its unintended consequences
- [x] Survey state expiry discussions on bitcoin-dev
- [x] Catalog covenant proposals relevant to state management
- [x] Map UTXO growth data and trends
- [ ] Publish survey as a public resource

### Phase R2: Formalize the Problem
- [ ] Define the UTXO cost function (what are the real costs?)
- [ ] Analyze the SegWit discount as a pricing mechanism (what was its actual effect?)
- [ ] Model the externality of data inscriptions on node operators
- [ ] Compare with other UTXO-based chains (Ethereon, Cardano, Litecoin)

### Phase R3: Propose Research Directions
- [ ] Draft a UTXO fee market proposal (not a solution — a framing)
- [ ] Evaluate state expiry tradeoffs in a formal analysis
- [ ] Design a block weight refactoring that accounts for UTXO cost
- [ ] Submit to bitcoin-dev mailing list for discussion

### Phase R4: Build Simulation (If Useful)
- [ ] Simulate UTXO set growth under different fee models
- [ ] Model node operator costs under different scenarios
- [ ] Publish reproducible results

---

## Literature & References

### BIPs
| BIP | Title | Relevance |
|-----|-------|-----------|
| [BIP-141](https://github.com/bitcoin/bips/blob/master/bip-0141.mediawiki) | Segregated Witness | Current pricing mechanism; 4× witness discount |
| [BIP-119](https://github.com/bitcoin/bips/blob/master/bip-0119.mediawiki) | OP_CHECKTEMPLATEVERIFY | Covenant for output-constrained spending |
| [BIP-347](https://github.com/bitcoin/bips/pull/1525) | OP_CAT | Enables covenant construction |

### Research Papers
- **"Enhancing Bitcoin Transactions with Covenants"** (FC'17) — [PDF](https://fc17.ifca.ai/bitcoin/papers/bitcoin17-final28.pdf)
  - Formalizes covenant constructions in Bitcoin
  - Relevant to state management through output constraints
- **"SoK: Bitcoin Layer Two"** — Survey of L2 protocols and their state implications
- **"The Bitcoin UTXO Set: A Statistical Analysis"** — Data on UTXO growth patterns

### Mailing List Discussions
- **bitcoin-dev: "State expiry"** — Rusty Russell, Gregory Maxwell, et al.
  - [Thread archive search](https://lists.linuxfoundation.org/pipermail/bitcoin-dev/) (search "state expiry")
- **bitcoin-dev: "UTXO growth"** — Multiple threads on UTXO set scaling
- **bitcoin-dev: "Block weight reform"** — Proposals to adjust SegWit discount

### People to Follow
- **Rusty Russell** — Bitcoin Core contributor; state expiry discussions
- **Gregory Maxwell** — Original SegWit design; UTXO growth analysis
- **Anthony Towns** — Covenant design and analysis
- **Pieter Wuille** — SegWit, Taproot, signature aggregation
- **Andrew Poelstra** — Covenant research (CAT + Schnorr tricks)
- **Eric Lombrozo** — Original SegWit BIP author

### Community Resources
- [Bitcoin Optech](https://bitcoinops.org/) — Weekly newsletter; topics on covenants, SegWit, state management
- [Delving Bitcoin](https://delvingbitcoin.org/) — Technical discussion forum (successor to bitcoin-dev mailing list)
- [Bitcoin Stack Exchange](https://bitcoin.stackexchange.com/) — Tag: utxo, segwit, state

---

## What We Learned

1. **The problem is real but the solutions we proposed were not.** The Reddit thread was correct — without a market mechanism, any pricing is arbitrary.

2. **Bitcoin has no mechanism for pricing state storage.** The SegWit discount was not designed for this and fixing it is an open research problem.

3. **No one has solved this.** State expiry has been discussed for years with no consensus. UTXO fee markets are theoretical. This is a genuine open problem.

4. **The honest contribution is to reframe the question, not to pretend we have answers.** This document is that reframing.

---

*This is a research document, not a proposal. It exists to frame an open problem, not to claim a solution. No contact information is included because the ideas should stand on their own merit, not on who wrote them.*

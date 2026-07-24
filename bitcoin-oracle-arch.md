# Bitcoin Block Priority Oracle

## Problem

Bitcoin blocks have ~4 MWU (million weight units). Inscriptions (Ordinals, BRC-20, Runes) compete with financial transactions (payments, settlements, Lightning channel opens) for the same space. Miners optimize for fee revenue — if data inscriptions pay higher fees, financial transactions get priced out or delayed.

No consensus change required. No soft fork. No hard fork.

## Solution

A **sidecar oracle + Stratum v2 plugin** that classifies transactions as **financial** or **data** before block template assembly, enabling a two-tier priority fee market within the existing block size limit.

## Architecture

```
Mempool ──> Oracle ──> Classified Pool ──> Template Builder ──> Stratum v2 ──> Miner
                │
                └──> Fee Advisor ──> Fee Estimator API
```

### 1. Transaction Classifier (Oracle)

**Input:** Raw transaction from mempool (via `getrawmempool` or `testmempoolaccept`).

**Classification logic (in order):**

| Rule | Classification | Rationale |
|------|---------------|-----------|
| OP_RETURN data > 80B | DATA | Non-standard data carrier |
| Witness data > (input count × 400B) | DATA | High witness ratio = inscription |
| Contains Taproot script path spend with large witness (> 500 vB) | DATA | Typical Ordinal inscription |
| Standard P2PKH / P2WPKH / P2TR keypath | FINANCIAL | Normal payment |
| Multisig, time-locks, HTLCs | FINANCIAL | Lightning / DeFi |
| BIP-125 (CPFP/RBF) flagged | FINANCIAL | Fee-bumping for time-sensitive tx |
| Fallback | FINANCIAL | Default safe classification |

**False positive mitigation:** DATA classification requires confidence ≥ 0.7. Borderline cases tagged `UNCERTAIN` and fall through to FINANCIAL.

### 2. Priority Fee Market

Two virtual pools:

```
Financial Pool:     tx with FINANCIAL tag, sorted by fee-rate
Data Pool:          tx with DATA tag, sorted by fee-rate
```

**Allocation algorithm (per block template):**

```
Given block capacity C (4 MWU):
  financial_fee_floor = max(0, P50 financial fee-rate)
  data_fee_floor = max(0, P50 data fee-rate)

  # Financial transactions are never fully crowded out
  min_financial_allocation = min(C × 0.3, total_financial_weight)
  # Remainder split by fee-ratio
  remaining = C - min_financial_allocation
  fee_ratio = clamp(0.1, data_fee_floor / financial_fee_floor, 10.0)
  data_allocation = remaining × (fee_ratio / (1 + fee_ratio))
  financial_allocation = min_financial_allocation + remaining - data_allocation
```

**Result:** If data fees dominate → data gets more space, but financial always gets minimum 30% reservation. If fees are equal → 50/50 split. If financial fees dominate → financial gets priority.

### 3. Stratum v2 Plugin

Extends the Template Distribution Protocol (channel `0x74`):

**New message types:**

| Message | Direction | Payload |
|---------|-----------|---------|
| `SetClassificationRules` | Mining Service → Miner | Array of regex/opcode patterns |
| `ClassifiedTemplate` | Mining Service → Miner | Block template + per-tx tag (0=financial, 1=data, 2=uncertain) |
| `PriorityPreference` | Miner → Mining Service | `{financial_weight_ratio: 0.3..0.7, max_data_weight: 2 MWU}` |

**Flow:**

1. Mining Service publishes `ClassifiedTemplate` instead of `NewTemplate`.
2. Miner receives per-tx classification alongside standard template data.
3. Miner can optionally signal `PriorityPreference` to adjust the allocation.
4. If no `PriorityPreference` received, default 30% financial floor applies.

No changes to the mining hardware interface — only the template assembly layer.

### 4. Fee Estimator API

REST endpoint returning:

```json
{
  "financial": {
    "fastest": 120,  // sat/vB
    "hour": 45
  },
  "data": {
    "fastest": 200,
    "hour": 80
  },
  "allocation": {
    "financial_pct": 62,
    "data_pct": 38,
    "blocks_until_financial_congestion": 3
  }
}
```

Users see separate fee suggestions for financial vs data transactions. Wallets integrate the financial endpoint for optimal confirmation times.

### 5. Trust Model

The oracle does NOT need to be trustless for MVP:

| Component | Trust Model | Upgrade Path |
|-----------|-------------|-------------|
| Classifier | Centralized (pool-operated) | Open-source + verifiable classification proofs |
| Allocation | Deterministic from classification | On-chain commitment to allocation |
| Stratum messages | Signed by pool key | Future: aggregated attestation from multiple oracles |

**Phased decentralization:**

1. **Phase 1 (MVP):** Single pool runs the oracle, publishes classification rules open-source.
2. **Phase 2:** Multiple oracles, miner selects median classification via `PriorityPreference`.
3. **Phase 3:** Succinct classification proofs (see future work).

## Implementation Plan

### Phase 1 — Oracle Core (Weeks 1-4)

- Transaction classifier in Rust (using `rust-bitcoin`)
- Bitcoin Core RPC integration (`getrawmempool`, `decoderawtransaction`)
- Classification confidence scoring
- Test against mainnet mempool snapshot (100K transactions)

### Phase 2 — Fee Market + Template Builder (Weeks 5-7)

- Allocation algorithm
- Template assembly with classified transactions
- Performance benchmark (template generation time < 100ms)

### Phase 3 — Stratum v2 Plugin (Weeks 8-10)

- Stratum v2 protocol extension (rust-stratum)
- `ClassifiedTemplate` message
- `PriorityPreference` handling
- Integration test with mining simulator

### Phase 4 — Fee Estimator + Polish (Weeks 10-12)

- REST API for fee estimation
- Prometheus metrics
- Grafana dashboard
- Documentation + deployment guide

## Future Work

- **Classification proofs:** Merkle inclusion + opcode commitment so miners can independently verify classification.
- **MEV resistance:** Commit-reveal scheme for classification to prevent front-running.
- **Cross-pool coordination:** Federation of oracles with BFT consensus on classification.
- **Client-side validation:** Wallet-side classification to pre-negotiate with pool.

## Why This Works

1. **No consensus change:** Everything happens at the template assembly layer.
2. **Miners opt in voluntarily:** They keep full discretion via `PriorityPreference`.
3. **Market-driven:** Classification is a suggestion, not a rule. Miners who ignore it lose nothing; miners who use it attract financial tx fee flow.
4. **Backward compatible:** Unmodified miners see standard templates. Stratum v2 is already rolling out.

## Team

- **2 engineers** (Rust + Bitcoin protocol)
- **1 part-time** (mining ops / Stratum v2 integration)
- **Timeline:** 10-12 weeks to production

## Resources Needed

- Bitcoin Core node (archive, mainnet)
- Mining simulator (regtest + Stratum v2)
- Mainnet mempool data for test vectors

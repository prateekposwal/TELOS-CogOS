# Bitcoin Tools & Ecosystem — Complete Map

> Research conducted 2026-07-29 via live HTTP fetch of every listed URL.

---

## 1. DASHBOARD & VISUALIZATION TOOLS

### 1.1 mempool.space
- **URL:** https://mempool.space
- **What it does:** Full-featured mempool visualizer, block explorer, and fee dashboard. Open-source (AGPLv3, 2.8k ★ on GitHub).
- **Data:** Real-time mempool, fee rates, block templates, mining pool stats, Lightning Network stats, historical fee charts, transaction tracking, address lookup, audit dashboard.
- **Pricing:** Free public instance. Self-hostable for free. Enterprise tier available.
- **API:** Full REST API at `/api/v1/`. Endpoints for fees (`/fees/recommended`), blocks, transactions, mempool, mining pools, Lightning. No auth required for read-only.
- **Self-host:** One-click install on Umbrel, RaspiBlitz, Start9, myNode, RoninDojo.
- **Relevance to Bitcoin Sahi:** THE most important tool. Self-hosted instance gives complete control over fee data, mempool analysis, and mining stats. Can feed API directly into Sahi's cost models.
- **Live fee data fetched (2026-07-29):** `{fastestFee:2, halfHourFee:1, hourFee:1, economyFee:1, minimumFee:1}` — all in sat/vB.

### 1.2 Clark Moody Bitcoin Dashboard
- **URL:** https://bitcoin.clarkmoody.com/dashboard/
- **What it does:** Clean, real-time dashboard showing Bitcoin network health at a glance.
- **Data:** Current block height, difficulty, hash rate, mempool count, fee percentiles, price, market cap, next halving countdown, block time, fee rates (25th/50th/75th/90th percentiles).
- **Pricing:** Free. Donation-supported.
- **API:** No public API (page renders JS-based).
- **Relevance to Sahi:** Good reference UI for how a Bitcoin dashboard should look. Data is cross-reference.

### 1.3 Bitcoin Visuals
- **URL:** https://bitcoinvisuals.com
- **What it does:** Extensive library of Bitcoin charts and statistics. Historical time-series.
- **Data:** 50+ charts across: Blockchain (height, difficulty, hash rate, supply, chain size, block size/weight, tx/sec, tx/block, tx/day, fees in USD/BTC, fees/day, fees/MB, inputs/outputs per tx/day, volumes), Lightning (nodes, channels, capacity, eccentricity, clustering), bitcoind (bandwidth, peers, mempool, memory usage, min tx fee), Misc (future supply, Puell Multiple, 1-cent fee reward).
- **Pricing:** Free.
- **API:** No documented API. Data exported via CSV? Unclear.
- **Relevance to Sahi:** Historical fee data reference. Good for cross-validating fee models.

### 1.4 transactionfee.info / mainnet-observer
- **URL:** https://transactionfee.info → redirects to https://mainnet-observer.b10c.me
- **What it does:** Deep Bitcoin blockchain statistics with granular breakdowns. Open-source (by 0xB10C).
- **Data:** 100+ charts organized by: Transactions (SegWit%, Taproot%, RBF signaling, inscription share, versions, sizes), Payments, Inputs/Outputs (by script type — P2PKH/P2SH/P2WPKH/P2TR/P2A/P2MS/P2PK, OP_RETURN, Runestones, BIP47), Blocks (weight, size, empty blocks, coinbase analysis), Mining (hashrate, difficulty, work, block time), Mining Pools (hashrate distribution, centralization index, per-pool tracking), Fees (fee rate bands, sub-1-sat, zero-fee), UTXO Set (size, composition, spend age, delta by type), Bitcoin Script (signature lengths, pubkey compression, SigHash analysis).
- **Pricing:** Free. Open-source.
- **API:** Charts are statically generated. No live API.
- **Relevance to Sahi:** ULTRA relevant — the UTXO set composition, fee rate bands, and script-type distributions directly inform cost models. The Inscription tracking shows what's consuming blockspace.

### 1.5 Bitfeed
- **URL:** https://bitfeed.org
- **What it does:** Real-time mempool visualization with animated transaction flow.
- **Pricing:** Free. Open-source.
- **Relevance:** Eye candy / monitoring tool. Less useful for data extraction.

### 1.6 Timechain Calendar
- **URL:** https://timechaincalendar.com
- **What it does:** Bitcoin on-chain calendar showing significant dates (halvings, protocol events).
- **Pricing:** Free.
- **Relevance:** Context for timing analysis.

### 1.7 Learn Me A Bitcoin (Greg Walker)
- **URL:** https://learnmeabitcoin.com
- **What it does:** Comprehensive Bitcoin education resource plus blockchain explorer + developer tools.
- **Tools section:** Transaction builder, transaction splitter, script decoder, PSBT decoder, block hash calculator, address converter, ECDSA/Schnorr sign/verify.
- **Pricing:** Free.
- **Relevance:** Educational. Explorer can be used for debugging transactions. Tools useful for building.

---

## 2. FEE ESTIMATION TOOLS & APIs

### 2.1 mempool.space Fee API (live)
- **Endpoint:** `GET /api/v1/fees/recommended`
- **Response (live):** `{"fastestFee":2,"halfHourFee":1,"hourFee":1,"economyFee":1,"minimumFee":1}` sat/vB
- **Other endpoints:** `/api/v1/fees/mempool/blocks` — returns next block fee estimates per block. `/api/v1/prices` — current BTC price.
- **Rate limits:** Free tier: 1 req/sec. Paid: higher.
- **Relevance:** Primary fee data source. Use for real-time cost calculations.

### 2.2 Bitcoiner.live
- **URL:** https://bitcoiner.live
- **What it does:** Fee estimation with confidence levels (50%/80%/90%).
- **Data:** Live fee rates by max delay (30m, 1h, 2h, 3h, 6h, 12h, 24h). Shows total fee in $ per "typical" tx (141 vB native segwit). Lightning fee comparison.
- **API:** Documented at `/doc/api`. Lightweight.
- **Pricing:** Free. Donation-supported (LN + on-chain).
- **Relevance:** Directly shows what Sahi needs — fee per tx in $, confidence-based estimates.

### 2.3 BlockCypher Fee API
- **Endpoint:** `GET https://api.blockcypher.com/v1/btc/main`
- **Data:** `high_fee_per_kb`, `medium_fee_per_kb`, `low_fee_per_kb` (in satoshis per KB).
- **Pricing:** Free tier: 3 req/s, 100 req/hr. Paid from $119/mo with BTC discount.
- **Relevance:** Alternative fee data source. Less granular than mempool.space.

### 2.4 blockchain.com Fee Estimation
- **Available via:** Their API (undocumented in scraped page) but data available via their charts endpoint.
- **Pricing:** Free tier available. Paid for higher limits.
- **Relevance:** Large dataset. Useful for historical fee analysis.

### 2.5 Fee estimation in Bitcoin Core / bitcoind
- **RPC:** `estimatesmartfee` and `estimaterawfee` built into Bitcoin Core.
- **Data:** Uses internal fee estimation based on local mempool. Configurable confirmation targets.
- **Relevance:** Essential for node operators. Can be queried directly from a local node.

---

## 3. NODE MANAGEMENT TOOLS

### 3.1 Umbrel
- **URL:** https://umbrel.com
- **What it does:** Beautiful home server OS with one-click Bitcoin node + app store.
- **Hardware:** Umbrel Home ($549), Umbrel Pro ($699+, up to 32TB).
- **Software:** umbrelOS (free). App store includes: Bitcoin Core, LND, mempool, Thunderhub, BTCPay Server, Nostr, AI models (Ollama, DeepSeek R1, LLama 3), Pi-hole, Nextcloud, Plex, Home Assistant.
- **Pricing:** Software free. Hardware starts at $549.
- **Relevance:** Easiest way for Sahi users to run a Bitcoin node + mempool explorer. Self-hosted mempool gives local fee API.

### 3.2 Start9 (StartOS)
- **URL:** https://start9.com
- **What it does:** Sovereign computing platform. StartOS runs on personal servers.
- **Hardware:** Servers sold via store.start9.com.
- **Marketplace:** Bitcoin Core, LND, mempool, BTCPay, Thunderhub, Nostr, Matrix, many more.
- **Pricing:** Software free. Hardware sold separately.
- **Philosophy:** "Sovereign computing" — full ownership of data and infrastructure.
- **Relevance:** Alternative to Umbrel. Strong in privacy/sovereignty messaging. Same mempool integration.

### 3.3 RaspiBlitz
- **URL:** https://raspiblitz.org
- **What it does:** DIY Bitcoin & Lightning node on Raspberry Pi. Open-source (MIT).
- **Features:** Full Bitcoin node, Lightning (LND + CLN), mempool, BTCPay, many apps.
- **Pricing:** Free (software). Hardware: ~$100-200 for Pi + SSD.
- **Community:** Huge — Telegram groups in EN/DE/ES/IT/RU.
- **Relevance:** Low-cost node option for Sahi users. DIY ethos fits Bitcoin Sahi's audience.

### 3.4 myNode
- **URL:** https://mynodebtc.com
- **What it does:** Commercial Bitcoin & Lightning node platform.
- **Products:** Model Two ($399, Intel/16GB/2TB NVMe), Premium Software ($98/yr), Community Edition (free).
- **Apps:** 40+ including Bitcoin, LND, mempool, BTCPay, Thunderhub, RTL, LNbits, Specter, JoinMarket, Jam, Alby Hub, Netdata, Loop, Public Pool, Sphinx Chat.
- **Pricing:** Free Community Edition exists. Premium $98/yr. Hardware $399.
- **Relevance:** Most polished commercial node option. Premium+ includes support, remote backup, watchtower.

### 3.5 RoninDojo
- **Mentioned by mempool project. Samourai Wallet's node distro. Focused on privacy.**

### 3.6 nix-bitcoin
- **Mentioned by mempool project. NixOS-based Bitcoin node deployment.**

---

## 4. BLOCK EXPLORER APIs

### 4.1 mempool.space API
- **Base:** `https://mempool.space/api/v1/`
- **Major endpoints:**
  - `GET /fees/recommended` — fee estimates (fastest/halfHour/hour/economy/minimum)
  - `GET /blocks/{height}` — block data
  - `GET /address/{address}` — address info
  - `GET /address/{address}/txs` — address transactions
  - `GET /tx/{txid}` — transaction details
  - `GET /mempool` — mempool info
  - `GET /mempool/recent` — recent mempool transactions
  - `GET /lightning/statistics/latest` — LN stats
  - `GET /mining/pools/{slug}` — mining pool stats
- **Auth:** Optional for read-only. No token needed for basic queries.
- **Pricing:** Free public instance. Enterprise for higher limits.
- **Relevance:** THE primary API for Sahi's fee and block space data.

### 4.2 Blockstream.info API
- **URL:** https://blockstream.info
- **API:** Similar to mempool.space (mempool.info is the API backend).
- **Endpoints:** Block, tx, address, mempool.
- **Pricing:** Free.
- **Relevance:** Redundant with mempool.space but useful as fallback.

### 4.3 Blockchain.com Explorer API
- **URL:** https://www.blockchain.com/explorer
- **Data:** Live blocks, transactions, mempool, prices, market cap. Covers BTC, ETH, SOL, BCH, and more.
- **API:** Exists but less documented on front page. Has developer docs at `/explorer/docs`.
- **Pricing:** Free tier + paid.
- **Relevance:** Large dataset, good for historical data. But less granular than mempool.space for fee analysis.

### 4.4 BlockCypher API
- **URL:** https://www.blockcypher.com/dev/bitcoin/
- **What it does:** RESTful JSON API for Bitcoin + 5 other blockchains.
- **Data:** Blockchain overview, blocks, transactions, addresses, wallets, HD wallets, confidence factor, metadata, asset API, address forwarding, events/hooks (WebHooks + WebSockets).
- **Unique features:** Confidence Factor (probability of double-spend), Address Forwarding (auto-forward with processing fees), WebHook/WebSocket event system.
- **Free tier:** 3 req/s, 100 req/hr. Read-only GET calls don't need a token.
- **Paid:** From $119/mo (10% discount with BTC).
- **SDKs:** Ruby, Python, Go (official). Node, Java, PHP (deprecated). .NET (community).
- **Relevance:** Useful for transaction broadcasting, confidence checks, and address monitoring.

---

## 5. BITCOIN DATA ANALYSIS TOOLS & DATASETS

### 5.1 Coin Metrics (now Talos)
- **URL:** https://coinmetrics.io → now part of https://www.talostrading.com
- **What it does:** Institutional-grade digital asset data. Market data, on-chain data, pricing, indexes, classification (datonomy).
- **Data:** Network Data Pro (full blockchain data), Atlas (blockchain search engine), Market Data Feed/Pro, Reference Rates, Indexes.
- **Pricing:** Paid, institutional. Free tier through Coin Metrics Community (limited).
- **API:** Robust API at docs.coinmetrics.io. Python and other SDKs.
- **Relevance:** Premium on-chain data source if Sahi needs institutional-grade historical data.

### 5.2 BTC.com
- **URL:** https://www.btc.com
- **What it does:** Block explorer, mining pool. Now pivoted heavily to AI Computing Futures and AI Ecosystem.
- **Status:** Mining pool still exists but site focus has shifted to AI.
- **Relevance:** Diminished. Still a mining pool reference.

### 5.3 CryptoQuant (endurance.cryptoquant.com)
- **What it does:** On-chain and market data analytics.
- **Pricing:** Paid. Free tier has limited charts.
- **Relevance:** Premium data for exchange flows, miner reserves, etc.

### 5.4 Dune Analytics
- **URL:** https://dune.com (blocked 403)
- **What it does:** Community-driven blockchain analytics. SQL-based querying.
- **Pricing:** Free tier. Paid for higher compute.
- **Relevance:** If they support Bitcoin dashboards, could be used for custom analytics.

### 5.5 Hive.one
- **URL:** https://hive.one
- **What it does:** Maps Twitter communities and influential accounts. Indexed ~40M accounts.
- **Status:** Stopped updating May 2023 due to Twitter API pricing changes.
- **Relevance:** Was useful for finding notable Bitcoin accounts. Legacy only.

### 5.6 Jameson Lopp's Bitcoin Information
- **URL:** https://www.lopp.net/bitcoin-information.html
- **What it does:** The definitive curated directory of ALL Bitcoin resources.
- **Sections include:** Getting Started, Wallets, Running a Node, Security, Buying/Earning, History, Fee Estimates, Privacy, Classes, Technical Resources, Developer Tools, Block Explorers, Books, Careers, Network Statistics, Mining, News, Investment Theses, Visualizations, Data Anchoring, Economics, and more.
- **Relevance:** Master index of everything Bitcoin. Essential reference for discovering tools.

---

## 6. MINING POOL STATS & DASHBOARDS

### 6.1 mempool.space Mining Dashboard
- **URL:** https://mempool.space/mining
- **Data:** Hashrate (pool distribution), block rewards, fee revenue, block size, mining pool list with hashrate share, time since last block.
- **API:** `/api/v1/mining/pools/{slug}` for individual pool data.
- **Relevance:** Primary mining data source for Sahi. Shows which pools are mining what, fee revenue trends.

### 6.2 mainnet-observer Mining Pool Charts
- **URL:** https://mainnet-observer.b10c.me
- **Data:** Hashrate distribution, centralization index, per-pool charts (AntPool, F2Pool, Foundry, MARAPool, Ocean, ViaBTC, Unknown), BIP-110 signaling, BIP-54 coinbase compliance, ephemeral dust, P2A first mining.
- **Relevance:** Deep historical mining pool analysis. Centralization index is valuable for Sahi's risk models.

### 6.3 OCEAN Mining
- **URL:** https://ocean.xyz
- **What it does:** Decentralized mining pool. Allows miners to assemble their own block templates (template distribution).
- **Relevance:** Relevant for block space analysis — OCEAN allows individual miners to choose which transactions to include.

### 6.4 Foundry USA
- **URL:** https://foundrydigital.com
- **What it does:** Largest Bitcoin mining pool in North America. Institutional.
- **Relevance:** They recently polled miners on BIP-110 signaling. Major force in mining centralization.

---

## 7. UTXO ANALYSIS TOOLS

### 7.1 mainnet-observer UTXO Charts (best available)
- **URL:** https://mainnet-observer.b10c.me
- **Charts:**
  - UTXO count (size) over time
  - UTXO composition by script type (P2PKH, P2SH, P2WPKH, P2WSH, P2TR, P2A, P2MS, P2PK)
  - UTXO Delta by Script Type (net change per day)
  - UTXO Spend Age (age distribution of spent UTXOs in blocks)
- **Relevance:** Directly relevant to Bitcoin Sahi. UTXO set size and composition directly affects:
  - How much blockspace is needed
  - Fee competition dynamics
  - Cost of consolidation transactions

### 7.2 Bitcoin Visuals UTXO-related charts
- **URL:** https://bitcoinvisuals.com
- **Data:** Inputs/tx, Inputs/day, Outputs/tx, Outputs/day, Input/Output Volumes, Tx size, Tx vsize.
- **Relevance:** Historical trends in UTXO behavior.

### 7.3 Unchained (collaborative custody / multisig)
- **URL:** https://unchained.com/blog
- **What it does:** Collaborative custody platform. Educational blog on UTXO management, multisig, inheritance.
- **Relevance:** Their blog covers practical UTXO management. Useful for understanding how real users manage UTXOs.

---

## 8. INSCRIPTION / ORDINALS TRACKING TOOLS

### 8.1 Ordinals.com
- **URL:** https://ordinals.com
- **What it does:** The official Ordinals explorer. Lists latest inscriptions, blocks, collections, runes.
- **Data:** Live inscription feed, inscription detail (content, sat location), block-by-block explorer.
- **API:** GitHub: https://github.com/ordinals/ord (open-source ord client).
- **Pricing:** Free.
- **Relevance:** Critical for tracking blockspace consumption by inscriptions. The ord client can be run locally.

### 8.2 mainnet-observer Inscription Charts
- **URL:** https://mainnet-observer.b10c.me
- **Charts:**
  - % of transactions revealing an inscription
  - Transactions revealing inscriptions (daily count)
  - Inputs revealing an inscription
- **Relevance:** Quantifies how much blockspace Ordinals/Inscriptions consume.

### 8.3 Bitcoin Magazine article (July 2026)
- **Title:** "I Scanned the Entire Bitcoin Blockchain for Images. What I Found Will Shock You"
- **Key finding:** All images ever inscribed on Bitcoin were scanned and cataloged. Article addresses the "junk data" debate around BIP-110.

---

## 9. TOOLS FOR NODE OPERATOR COST UNDERSTANDING

### 9.1 mempool.space (cost visibility)
- **Self-hosted:** Shows exact fee data, mempool pressure, block space usage.
- **Cost-relevant data:** Fee rates, block fullness, mempool backlog, Lightning statistics.

### 9.2 Bitcoin Core RPC (`estimatesmartfee`)
- **Native fee estimation.** Shows fee rates for different confirmation targets.
- **RPC calls:** `getmempoolinfo`, `getblockstats`, `gettxoutsetinfo`, `getnetworkhashps`.

### 9.3 Netdata (in myNode app store)
- **URL:** https://www.netdata.cloud
- **What it does:** Real-time server monitoring. CPU, RAM, disk, network.
- **Relevance:** For node operators tracking hardware costs.

### 9.4 Node hardware comparison
- **Umbrel Home:** $549 (4GB RAM, 1TB SSD) to $699+ (32TB)
- **myNode Model Two:** $399 (Intel, 16GB RAM, 2TB NVMe)
- **RaspiBlitz DIY:** ~$100-200 (Pi 4/5 + SSD + case)
- **Start9:** Server pricing varies
- **Bitcoin Sahi relevance:** Cost analysis should factor in hardware + bandwidth + electricity.

### 9.5 Node bandwidth costs
- **Bitcoin Core bandwidth:** ~5-10 GB/day download, ~5-20 GB/day upload (varies by configuration).
- **Initial sync:** ~500-700 GB.
- **Relevance:** Bandwidth costs matter for cloud-hosted nodes.

---

## 10. RESEARCH ORGANIZATIONS & THINK TANKS

### 10.1 Bitcoin Optech
- **URL:** https://bitcoinops.org
- **What it does:** Helps Bitcoin businesses integrate scaling technology. Weekly newsletter, podcast, workshops, case studies.
- **Key resource:** Weekly newsletter (#415 as of July 2026) covering protocol changes, service announcements, releases, notable code changes. Their Matrix room analyses software/services.
- **Topics:** Full aggregation of BIP340 signatures, formal verification of Bitcoin protocol, covenant proposals, LN improvements.
- **Supporters:** BitGo, Coinbase, Kraken, BitMEX, Ledger, Square, Fidelity, Bitstamp, Unchained Capital, and many more.
- **Relevance:** Essential reading for staying current with Bitcoin protocol development. Their Matrix room specifically analyzes Bitcoin services.

### 10.2 Bitcoin Policy Institute
- **URL:** Mentioned in Bitcoin Magazine news — State Department partnership.
- **Focus:** Bitcoin policy research. Working with US State Department on "Freedom Tech Program."
- **Relevance:** Policy research that affects Bitcoin regulation and adoption.

### 10.3 Bitcoin Magazine (BTC Inc)
- **URL:** https://bitcoinmagazine.com
- **What it does:** Oldest Bitcoin publication (since 2012). News, technical analysis, market coverage.
- **Sections:** News, Business, Culture, Markets, Politics, Takes, Technical, Guides.
- **Parent:** BTC Inc / Nakamoto Inc (NASDAQ: NAKA).
- **Also runs:** Bitcoin Conference, Bitcoin Magazine Books, UTXO Management.
- **Relevance:** News and analysis. The "Technical" section covers protocol-level changes (e.g., BIP-110 coverage).

### 10.4 River Financial Research
- **URL:** https://river.com/research (and https://river.com/learn)
- **What it does:** Bitcoin research. Free educational content on mining, storage, markets, technology.
- **Relevance:** High-quality explainers. Their mining research is particularly strong.

### 10.5 BCAP (Bitcoin Consensus Analysis Project)
- **URL:** https://bitcoin-cap.github.io/bcap/
- **What it does:** Open-source framework for analyzing Bitcoin consensus stakeholders and risks.
- **Stakeholders mapped:** Economic Nodes, Investors, Media Influencers, Miners, Protocol Developers, Users & App Developers.
- **Relevance:** Framework for understanding how different stakeholders affect Bitcoin's evolution — relevant for cost/risk modeling.

### 10.6 Jameson Lopp / Casa
- **URL:** https://www.lopp.net
- **What it does:** Bitcoin security engineer (Casa). Maintains the most comprehensive Bitcoin resources page. Creator of Statoshi (Bitcoin Core monitoring).
- **Relevance:** Statoshi gives real-time node metrics (not currently active). Resource page is the best directory.

### 10.7 Fulmo
- **URL:** https://fulmo.org
- **What it does:** Bitcoin education organization. Manages RaspiBlitz donations.
- **Relevance:** Community-oriented education.

### 10.8 Stanford Blockchain / Crypto
- **URL:** https://crypto.stanford.edu (down for maintenance at time of fetch)
- **What it does:** Academic research on cryptocurrency protocols, privacy, scalability.
- **Relevance:** Academic research feed.

---

## 11. ADDITIONAL TOOLS & RESOURCES NOTED

### 11.1 Bitcoin Search
- **URL:** https://bitcoinsearch.xyz
- **What it does:** Search engine for Bitcoin content.

### 11.2 fork-observer
- **URL:** https://fork.observer
- **What it does:** Real-time blockchain fork monitoring. Shows fork status, invalid blocks, lagging nodes.
- **Open-source:** https://github.com/0xb10c/fork-observer
- **Relevance:** Critical for detecting chain splits — relevant if BIP-110 or other forks occur.

### 11.3 Lightning Network Statistics (via mempool.space API)
- **Live data (2026-07-29):**
  - Nodes: 17,260 (slight decrease from 17,282 previous week)
  - Channels: 38,911 (decrease from 39,224)
  - Total capacity: 449.6 BTC (~$29M USD)
  - Tor nodes: 8,761 (50.7%)
  - Clearnet nodes: 4,681
  - Avg channel capacity: 11,555,628 sat
  - Avg fee rate: 859 ppm
  - Med fee rate: 100 ppm
- **Relevance:** Lightning stats for cost-of-payment comparisons.

### 11.4 CoinDesk / CoinTelegraph / The Block
- General crypto news. Less Bitcoin-specific than Bitcoin Magazine.

### 11.4 Planaria Network
- **URL:** https://planaria.network — archived. Was a Bitcoin SV historical archive.

---

## 12. KEY INSIGHTS FOR BITCOIN SAHI

### Block Space Market Summary (July 2026)
- **Fees:** VERY LOW — fastest 2 sat/vB, economy 1 sat/vB. This is near the floor.
- **Mempool:** Nearly empty. Fee competition is minimal.
- **Hashrate:** 847 EH/s (as per blockchain.com). Network extremely secure.
- **Blocks:** ~144/day typical. Block 960,114 as of fetch time.
- **Inscriptions:** Still consuming blockspace but at lower volume than 2023-2024 peaks.
- **Lightning:** ~17K nodes, 39K channels, ~450 BTC capacity. Slightly declining channel count.

### BIP-110 Context
- BIP-110 proposes restricting arbitrary data in Bitcoin transactions (targeting inscriptions/Ordinals).
- Less than 1% miner signaling as of July 2026.
- Major debate in the community. Would affect blockspace demand if enacted.
- **Sahi relevance:** If BIP-110 activates, inscription-related blockspace demand drops significantly, potentially lowering fees further. If it fails, inscriptions continue consuming blockspace.

### Data Sources Available to Sahi
| Data | Source | Type | Cost |
|------|--------|------|------|
| Fee rates | mempool.space API | REST (live) | Free |
| Block details | mempool.space / blockstream.info | REST | Free |
| UTXO set stats | mainnet-observer | Charts | Free |
| Mining pool stats | mempool.space / mainnet-observer | REST + Charts | Free |
| Historical fees | Bitcoin Visuals / mainnet-observer | Charts/CSV? | Free |
| Inscription volume | mainnet-observer / ordinals.com | REST + Charts | Free |
| Lightning stats | mempool.space API | REST | Free |
| Mempool backlog | mempool.space API | REST | Free |
| Consensus/forks | fork-observer | Real-time | Free |
| Node monitoring | Bitcoin Core RPC + Netdata | Local | Free |
| Institutional data | Coin Metrics / CryptoQuant | API | Paid |

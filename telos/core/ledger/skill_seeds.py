"""
Skill Seeds — Knowledge scaffolds for the Capital Guardian + Strategy Lab.

These are TOC-derived skill scaffolds, indexed into the SkillLibrary exactly
like runtime-learned skills (Axiom 3.3 Option Decay applies equally).

Provenance model
----------------
Each seed is built from *public bibliographic metadata and the book's
publicly-known structure* (concept map, doctrine, formulas), NOT from
full-text reading. Everything chapter-specific carries `verified: False`
and must be confirmed against the actual books when legit copies land
(see knowledge_library/books/README.md acquisition manifest).

Schema fidelity notes (assumptions, mirroring the runtime's own usage)
----------------------------------------------------------------------
- `Skill.trajectory` is typed `Any`; the ExperienceManager stores dicts
  (`{"intent_type", "confidence", "params"}`). Seeds follow the same shape
  with an added `procedure` list = the canonical decision loop the skill encodes.
- `Skill.fingerprint` in the runtime is `md5(state.tobytes())[:12]` (see
  `SkillLibrary.find_relevant_skills`). Each seed therefore declares a
  `canonical_state` numpy array in `domain_config` and its fingerprint is
  derived from it the exact same way, so real state matching works.
- `utility_score` = 0.5 for all seeds: above the 0.3 utility-floor eviction
  threshold, below overconfident 1.0, because content is TOC-derived.
  Re-score after chapter-level ingestion.
"""

from __future__ import annotations

import hashlib
from typing import Dict, List, Optional

import numpy as np

from telos.core.ledger.skill_library import Skill

__all__ = [
    "SEED_MANIFEST",
    "SEED_SKILL_IDS",
    "build_capital_guardian_seed",
    "build_microstructure_seed",
    "build_crypto_framing_seed",
    "build_position_sizing_seed",
    "seed_by_id",
    "seed_skill_library",
    "validate_seed",
]

# ── Shared helpers ──────────────────────────────────────────────────────────

def _fingerprint(state: np.ndarray) -> str:
    """Mirror SkillLibrary.find_relevant_skills fingerprint computation.
    state: the state for this operation
"""
    return hashlib.md5(state.tobytes()).hexdigest()[:12]


def _source_book(title: str, author: str, publisher: str, year: int,
                 isbn13: str, openlibrary: str, role: str) -> Dict:
    return {
        "title": title,
        "author": author,
        "publisher": publisher,
        "year": year,
        "isbn13": isbn13,
        "openlibrary": openlibrary,
        "role": role,
    }


# ── 1. capital_guardian ─────────────────────────────────────────────────────

def build_capital_guardian_seed(utility: float = 0.5) -> Skill:
    """Risk-first doctrine seed — Grant (Trading Risk) + Elder 2% rule + Aziz.

    The Capital Guardian skill governs every capital deployment decision:
    how much risk per trade, where stops live, when the kill-switch fires,
    and how edge is measured (expectancy / R-multiples).
    
    utility: the utility for this operation
"""
    canonical_state = np.array([1.0, 0.0, 0.5], dtype=np.float64)  # equity, drawdown, risk posture
    source_books = [
        _source_book(
            "Trading Risk (Enhanced Profitability through Risk Control)",
            "Kenneth L. Grant", "Wiley", 2004, "978-0-470-25196-6",
            "/works/OL5758266W", "primary",
        ),
        _source_book(
            "Trading for a Living", "Alexander Elder", "Wiley", 1993,
            "978-0-471-59224-2", "/works/OL1392204W", "supporting (2% rule)",
        ),
        _source_book(
            "Advanced Techniques in Day Trading", "Andrew Aziz",
            "CreateSpace", 2016, "978-1-539-09176-1", "/works/OL28147731W",
            "supporting (1-2% rule, sizing formula)",
        ),
    ]
    metadata = {
        "kind": "knowledge_seed",
        "status": "scaffold_toc_derived",       # -> "filled" after book ingestion
        "toc_verified": False,
        "source_books": source_books,
        "primary_source": "grant_trading_risk",
        "concept_map": {
            "risk_control": [
                "probability of ruin", "expected return vs variance",
                "drawdown", "risk budgeting",
            ],
            "position_sizing_rule": [
                "Elder 2% rule", "Aziz 1-2% rule", "fixed-fractional sizing",
                "stop placement",
            ],
            "behavioral_discipline": [
                "stop discipline", "kill-switch", "overtrading",
                "revenge trading",
            ],
            "expectancy_math": [
                "expectancy E = (Pw*W) - (Pl*L)", "edge", "R-multiples",
            ],
            "portfolio_risk": [
                "correlation", "concentration limits", "circuit breakers",
            ],
        },
        "knowledge_fields": [
            "per_trade_risk_budget", "stop_placement_protocol",
            "kill_switch_conditions", "expectancy_formula",
            "drawdown_circuit_breaker", "portfolio_concentration_limits",
        ],
        "decision_rules": [
            "size = (equity * risk%) / (entry - stop)",
            "risk no more than 1-2% of equity per trade; halt on breach",
            "kill-switch: flatten all positions when daily drawdown >= X% (default 3%)",
            "only trade when expectancy E > 0 and reward:risk >= 2:1 (configurable)",
            "no new positions after N consecutive losses (configurable)",
        ],
        "failure_modes": [
            "risk % miscalculated on leverage/derivatives (notional vs equity)",
            "kill-switch overridden during drawdown (behavioral)",
            "expectancy computed on raw P&L instead of R-multiples",
            "stop too wide -> effective risk exceeds budget",
            "correlated positions treated as independent risks",
        ],
        "ingestion_hooks": [
            {"chapter": "Grant Ch 1-3 (risk control foundations)", "fills": ["per_trade_risk_budget", "expectancy_formula"], "verified": False},
            {"chapter": "Grant Ch 4-6 (drawdown / probability of ruin)", "fills": ["drawdown_circuit_breaker"], "verified": False},
            {"chapter": "Grant Ch 7-9 (leverage & portfolio risk)", "fills": ["portfolio_concentration_limits"], "verified": False},
            {"chapter": "Elder 'Trading for a Living' 2% / 6% rules", "fills": ["per_trade_risk_budget", "kill_switch_conditions"], "verified": False},
            {"chapter": "Aziz money-management chapters", "fills": ["stop_placement_protocol"], "verified": False},
        ],
        "required_after_reading": [
            "Grant's exact risk-control formulas and verified chapter titles",
            "Elder's exact 2% and 6% rule statements",
            "Aziz's sizing formula with worked example",
            "confirmed TOC chapter titles for all three sources",
        ],
        "utility_basis": "toc-derived scaffold; rescore after chapter ingestion",
        "canonical_fingerprint": _fingerprint(canonical_state),
    }
    return Skill(
        skill_id="capital_guardian",
        fingerprint=metadata["canonical_fingerprint"],
        trajectory={
            "kind": "knowledge_seed",
            "intent_type": "apply_risk_first_doctrine",
            "confidence": utility,
            "procedure": [
                "1. compute per-trade risk budget = equity * max_risk_per_trade",
                "2. place stop so (entry - stop) respects the budget",
                "3. check kill-switch: flatten if daily drawdown >= threshold",
                "4. verify expectancy E > 0 and R:R >= minimum before entry",
                "5. log position + risk attribution to ledger",
            ],
            "params": {
                "max_risk_per_trade": 0.02,   # 1-2% band, 0.02 default
                "kill_switch_daily_drawdown": 0.03,
                "min_reward_risk": 2.0,
                "max_consecutive_losses": 5,
            },
        },
        utility_score=utility,
        domain_config={
            "domain": "trading_risk",
            "canonical_state": canonical_state,
            "risk_params": {
                "max_risk_per_trade": 0.02,
                "kill_switch_daily_drawdown": 0.03,
                "min_reward_risk": 2.0,
                "max_consecutive_losses": 5,
            },
        },
        metadata=metadata,
    )


# ── 2. microstructure ────────────────────────────────────────────────────────

def build_microstructure_seed(utility: float = 0.5) -> Skill:
    """Market microstructure seed — Harris (Trading and Exchanges).

    How orders, spreads, liquidity, and adverse selection actually work,
    and why naive market orders pay a hidden tax (half-spread + impact).
    
    utility: the utility for this operation
"""
    canonical_state = np.array([0.0, 1.0, 0.0, 1.0], dtype=np.float64)  # book, side, spread, depth
    metadata = {
        "kind": "knowledge_seed",
        "status": "scaffold_toc_derived",
        "toc_verified": False,
        "source_books": [
            _source_book(
                "Trading and Exchanges: Market Microstructure for Practitioners",
                "Larry Harris", "Oxford University Press", 2003,
                "978-0-19-514470-3", "/books/OL18178856M", "primary",
            ),
        ],
        "primary_source": "harris_trading_exchanges",
        "concept_map": {
            "order_types": [
                "market vs limit", "stop orders", "pegged orders",
                "icebergs", "order precedence rules",
            ],
            "trading_arrangements": [
                "dealer markets", "auction/order-driven markets",
                "specialists", "ECNs/ATS", "fragmentation",
            ],
            "liquidity": [
                "depth", "resilience", "tightness/spread",
                "price impact", "adverse selection",
            ],
            "information": [
                "informed vs uninformed flow", "adverse selection",
                "spread as adverse-selection tax", "signal extraction",
            ],
            "execution_costs": [
                "half-spread cost", "market impact", "timing risk",
                "opportunity cost",
            ],
        },
        "knowledge_fields": [
            "spread_components", "adverse_selection_measure",
            "price_impact_curve", "limit_order_fill_probability",
            "market_vs_limit_costs", "liquidity_regimes",
        ],
        "decision_rules": [
            "naive market orders pay half-spread + impact; prefer limit orders when fill risk is manageable",
            "size orders to <= X% of displayed depth to bound price impact",
            "adverse selection is priced into the spread - crossing more often cannot 'beat' it",
            "when quoted spread > model fair spread, execution is overpriced: queue or venue-shop",
        ],
        "failure_modes": [
            "market order on a thin book -> impact far exceeds commission",
            "limit order never fills -> missed trade; fills on toxic flow only (adverse selection)",
            "ignoring queue position / time priority",
            "treating displayed depth as total liquidity (icebergs, spoofing)",
        ],
        "ingestion_hooks": [
            {"chapter": "Harris Part I (Ch 1-5: trading, orders, market structure)", "fills": ["spread_components", "market_vs_limit_costs"], "verified": False},
            {"chapter": "Harris Part II (Ch 6-9: liquidity, volatility, transparency)", "fills": ["liquidity_regimes", "adverse_selection_measure"], "verified": False},
            {"chapter": "Harris Part III (Ch 10-14: brokers, dealers, exchanges)", "fills": ["limit_order_fill_probability"], "verified": False},
            {"chapter": "Harris Part IV/V (Ch 15-16+: participants, trading)", "fills": ["price_impact_curve"], "verified": False},
        ],
        "required_after_reading": [
            "verified chapter titles from OUP edition",
            "Harris's spread decomposition and price-impact formulas",
            "adverse-selection model specifics",
        ],
        "utility_basis": "toc-derived scaffold; rescore after chapter ingestion",
        "canonical_fingerprint": _fingerprint(canonical_state),
    }
    return Skill(
        skill_id="microstructure",
        fingerprint=metadata["canonical_fingerprint"],
        trajectory={
            "kind": "knowledge_seed",
            "intent_type": "execute_with_awareness",
            "confidence": utility,
            "procedure": [
                "1. read current spread + displayed depth for the venue",
                "2. estimate price impact for intended size (impact curve)",
                "3. decide market vs limit: limit if fill risk acceptable",
                "4. bound order size to a fraction of depth",
                "5. log execution cost attribution (spread + impact + timing)",
            ],
            "params": {
                "max_impact_pct": 0.05,
                "max_size_pct_of_depth": 0.10,
                "prefer_limit_orders": True,
            },
        },
        utility_score=utility,
        domain_config={
            "domain": "market_microstructure",
            "canonical_state": canonical_state,
            "risk_params": {
                "max_impact_pct": 0.05,
                "max_size_pct_of_depth": 0.10,
                "min_liquidity_units": 0.0,
            },
        },
        metadata=metadata,
    )


# ── 3. crypto_framing ───────────────────────────────────────────────────────

def build_crypto_framing_seed(utility: float = 0.5) -> Skill:
    """Cryptoasset framing seed — Burniske & Tatar (Cryptoassets).

    Valuation under extreme uncertainty: NVT, adoption S-curves, network
    effects, and the regulatory/legacy risk layer that equities don't have.
    
    utility: the utility for this operation
"""
    canonical_state = np.array([1.0, 1.0, 0.0], dtype=np.float64)  # network, adoption, regulatory
    metadata = {
        "kind": "knowledge_seed",
        "status": "scaffold_toc_derived",
        "toc_verified": False,
        "source_books": [
            _source_book(
                "Cryptoassets: The Innovative Investor's Guide to Bitcoin and Beyond",
                "Chris Burniske & Jack Tatar", "McGraw-Hill Education", 2018,
                "978-1-26-002667-2", "/books/OL26939457M", "primary",
            ),
        ],
        "primary_source": "burniske_cryptoassets",
        "concept_map": {
            "asset_class": [
                "cryptoassets as a new asset class",
                "risk/return profile vs stocks/bonds/gold", "correlation",
            ],
            "valuation": [
                "NVT ratio", "utility analysis / cash-flow analog",
                "valuation uncertainty", "band not point estimate",
            ],
            "adoption": [
                "S-curve adoption", "Metcalfe's law / network effects",
                "cryptoasset internet of value (CIA)",
            ],
            "risk": [
                "regulatory/legacy risk", "technology risk",
                "market structure risk", "token supply/emissions",
            ],
            "portfolio": [
                "position sizing for volatility", "rebalancing",
                "drawdown expectations in bear regimes",
            ],
        },
        "knowledge_fields": [
            "nvt_ratio", "adoption_curve_phase", "network_effect_metric",
            "regulatory_risk_register", "valuation_uncertainty_bounds",
            "correlation_to_traditional_assets",
        ],
        "decision_rules": [
            "value via NVT + adoption curve, not price alone; flag regime when NVT >> historical band",
            "size crypto positions for 70-90% drawdown tolerance (multi-year horizon)",
            "regulatory event = repricing risk; predefine exit / kill conditions",
            "network effects dominate: favor assets with growing active usage, not just price",
        ],
        "failure_modes": [
            "treating NVT as a timing signal instead of a valuation band",
            "underestimating regulatory / legacy risk (exchange, custody, legal)",
            "ignoring token emissions / dilution in supply math",
            "anchoring on historical correlation that breaks in regime shifts",
        ],
        "ingestion_hooks": [
            {"chapter": "Burniske Part I (rise of cryptoassets, Bitcoin history)", "fills": ["adoption_curve_phase"], "verified": False},
            {"chapter": "Burniske Part II (valuation: NVT, CIA, adoption)", "fills": ["nvt_ratio", "network_effect_metric", "valuation_uncertainty_bounds"], "verified": False},
            {"chapter": "Burniske Part III (portfolio management)", "fills": ["correlation_to_traditional_assets", "regulatory_risk_register"], "verified": False},
        ],
        "required_after_reading": [
            "exact NVT formula and band parameters",
            "adoption-curve model specifics",
            "risk table / portfolio guidance from Part III",
        ],
        "utility_basis": "toc-derived scaffold; rescore after chapter ingestion",
        "canonical_fingerprint": _fingerprint(canonical_state),
    }
    return Skill(
        skill_id="crypto_framing",
        fingerprint=metadata["canonical_fingerprint"],
        trajectory={
            "kind": "knowledge_seed",
            "intent_type": "frame_cryptoasset_regime",
            "confidence": utility,
            "procedure": [
                "1. compute NVT and compare to historical band",
                "2. locate asset on adoption S-curve (phase estimate)",
                "3. check regulatory risk register for open items",
                "4. size for drawdown tolerance, not short-term vol",
                "5. log regime framing + valuation uncertainty bounds",
            ],
            "params": {
                "nvt_band_high": 0.0,   # fill from book
                "drawdown_tolerance": 0.80,
                "rebalance_freq_days": 30,
            },
        },
        utility_score=utility,
        domain_config={
            "domain": "cryptoasset_valuation",
            "canonical_state": canonical_state,
            "risk_params": {
                "nvt_band_high": 0.0,
                "drawdown_tolerance": 0.80,
                "max_crypto_exposure_pct": 0.20,
            },
        },
        metadata=metadata,
    )


# ── 4. position_sizing ──────────────────────────────────────────────────────

def build_position_sizing_seed(utility: float = 0.5) -> Skill:
    """Position sizing seed — Vince (Mathematics of Money Management).

    Fixed-fractional sizing, optimal f, and the core doctrine: sizing,
    not entry, determines survival.
    
    utility: the utility for this operation
"""
    canonical_state = np.array([0.5, 0.5, 0.0], dtype=np.float64)  # win prob, payoff, drawdown
    metadata = {
        "kind": "knowledge_seed",
        "status": "scaffold_toc_derived",
        "toc_verified": False,
        "source_books": [
            _source_book(
                "The Mathematics of Money Management: Risk Analysis Techniques for Traders",
                "Ralph Vince", "Wiley", 1992, "978-0-471-54738-9",
                "/works/OL3503409W", "primary",
            ),
        ],
        "primary_source": "vince_math_money_management",
        "concept_map": {
            "sizing_philosophy": [
                "sizing, not entry, determines survival",
                "money management as the only long-run determinant",
            ],
            "fixed_fractional": [
                "f = fraction of equity risked", "geometric vs arithmetic growth",
                "variance drain",
            ],
            "optimal_f": [
                "maximizes geometric growth", "overbetting -> ruin despite positive expectancy",
                "f* estimation sensitivity",
            ],
            "drawdown": [
                "drawdown math", "recovery asymmetry (50% loss needs 100% gain)",
                "max adverse excursion",
            ],
            "portfolio": [
                "leverage space portfolios", "multi-market allocation",
                "risk of ruin",
            ],
        },
        "knowledge_fields": [
            "fixed_fractional_formula", "optimal_f_estimate",
            "variance_drain", "drawdown_recovery_math", "risk_of_ruin_formula",
        ],
        "decision_rules": [
            "risk a fixed fraction of equity per trade (default f = 2%); never exceed geometric-optimal f",
            "a 50% drawdown requires 100% recovery - size to survive worst-case streaks",
            "overbetting converts a positive-expectancy system into ruin; f* is a ceiling, not a target",
            "recompute f on the realized distribution, not point estimates",
        ],
        "failure_modes": [
            "betting > optimal f (the classic ruin path)",
            "sizing on total capital instead of risk capital / equity at risk",
            "ignoring variance drain (same expectancy, smaller geometric mean at high f)",
            "using sample-dependent f* without a margin of safety",
        ],
        "ingestion_hooks": [
            {"chapter": "Vince Ch 1-2 (money management basics, risk of ruin)", "fills": ["risk_of_ruin_formula"], "verified": False},
            {"chapter": "Vince Ch 3-4 (fixed-fractional, optimal f)", "fills": ["fixed_fractional_formula", "optimal_f_estimate"], "verified": False},
            {"chapter": "Vince Ch 5+ (leverage space, portfolios)", "fills": ["variance_drain", "drawdown_recovery_math"], "verified": False},
        ],
        "required_after_reading": [
            "Vince's exact optimal-f computation",
            "drawdown / risk-of-ruin formulas",
            "leverage-space portfolio math",
        ],
        "utility_basis": "toc-derived scaffold; rescore after chapter ingestion",
        "canonical_fingerprint": _fingerprint(canonical_state),
    }
    return Skill(
        skill_id="position_sizing",
        fingerprint=metadata["canonical_fingerprint"],
        trajectory={
            "kind": "knowledge_seed",
            "intent_type": "compute_position_size",
            "confidence": utility,
            "procedure": [
                "1. compute f = risk fraction of equity (default 0.02)",
                "2. size = (equity * f) / (entry - stop) per trade",
                "3. check size against optimal-f ceiling f*",
                "4. simulate worst-case streak drawdown; reject if ruin threshold hit",
                "5. log sizing decision + drawdown projection",
            ],
            "params": {
                "fixed_fractional_f": 0.02,
                "optimal_f_ceiling": 0.25,   # placeholder, fill from Vince
                "ruin_drawdown_threshold": 0.50,
            },
        },
        utility_score=utility,
        domain_config={
            "domain": "position_sizing",
            "canonical_state": canonical_state,
            "risk_params": {
                "fixed_fractional_f": 0.02,
                "optimal_f_ceiling": 0.25,
                "ruin_drawdown_threshold": 0.50,
            },
        },
        metadata=metadata,
    )


# ── Registry + seeding helpers ──────────────────────────────────────────────

SEED_MANIFEST: Dict[str, Dict] = {
    "capital_guardian": {
        "primary_book": "grant_trading_risk",
        "supporting_books": ["elder_trading_for_a_living", "aziz_advanced_day_trading"],
        "manifest_ref": "knowledge_library/books/README.md (row 1)",
    },
    "microstructure": {
        "primary_book": "harris_trading_exchanges",
        "supporting_books": [],
        "manifest_ref": "knowledge_library/books/README.md (row 2)",
    },
    "crypto_framing": {
        "primary_book": "burniske_cryptoassets",
        "supporting_books": [],
        "manifest_ref": "knowledge_library/books/README.md (row 3)",
    },
    "position_sizing": {
        "primary_book": "vince_math_money_management",
        "supporting_books": [],
        "manifest_ref": "knowledge_library/books/README.md (row 4)",
    },
}

SEED_SKILL_IDS: List[str] = list(SEED_MANIFEST.keys())

_SEED_BUILDERS: Dict[str, callable] = {
    "capital_guardian": build_capital_guardian_seed,
    "microstructure": build_microstructure_seed,
    "crypto_framing": build_crypto_framing_seed,
    "position_sizing": build_position_sizing_seed,
}


def seed_by_id(skill_id: str, utility: float = 0.5) -> Skill:
    """Return a single seed skill by id.
    skill_id: the skill id for this operation
    utility: the utility for this operation
"""
    if skill_id not in _SEED_BUILDERS:
        raise KeyError(
            f"Unknown seed skill_id {skill_id!r}; known seeds: {SEED_SKILL_IDS}"
        )
    return _SEED_BUILDERS[skill_id](utility=utility)


def seed_skill_library(lib: Optional[object] = None) -> object:
    """Index all seed scaffolds into a SkillLibrary.

    If `lib` is None, a fresh SkillLibrary(max_skills=100) is created.
    Returns the library (additive — never mutates existing skills).
    """
    if lib is None:
        from telos.core.ledger.skill_library import SkillLibrary
        lib = SkillLibrary(max_skills=100)
    for sid in SEED_SKILL_IDS:
        seed = _SEED_BUILDERS[sid]()
        lib.index_skill(seed)
    return lib


def validate_seed(skill: Skill) -> List[str]:
    """Return a list of schema violations (empty = valid seed).

    Mirrors SkillLibrary.index_skill's validation plus knowledge-seed
    completeness checks (TOC concept map, ingestion hooks, provenance).
    """
    violations: List[str] = []
    if not isinstance(skill.skill_id, str) or not skill.skill_id:
        violations.append("skill_id must be a non-empty string")
    if not isinstance(skill.fingerprint, str) or not skill.fingerprint:
        violations.append("fingerprint must be a non-empty string")
    if not isinstance(skill.utility_score, (int, float)):
        violations.append("utility_score must be a number")
    elif not (0.0 <= skill.utility_score <= 1.0):
        violations.append("utility_score out of [0,1] range")
    if not isinstance(skill.trajectory, dict):
        violations.append("trajectory must be a dict payload")
    m = skill.metadata
    for key in ("kind", "status", "source_books", "concept_map",
                "knowledge_fields", "decision_rules", "failure_modes",
                "ingestion_hooks", "required_after_reading"):
        if key not in m:
            violations.append(f"metadata missing {key!r}")
    if "concept_map" in m and not m["concept_map"]:
        violations.append("concept_map must be non-empty (TOC-derived)")
    hooks = m.get("ingestion_hooks", [])
    if not hooks:
        violations.append("ingestion_hooks must be non-empty")
    for h in hooks:
        if not h.get("chapter") or not h.get("fills"):
            violations.append("each ingestion_hook needs 'chapter' and 'fills'")
    if "canonical_state" not in skill.domain_config:
        violations.append("domain_config missing canonical_state (needed for fingerprint matching)")
    return violations

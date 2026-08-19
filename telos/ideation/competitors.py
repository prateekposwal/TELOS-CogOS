"""
Competitor-aware RE-SCORING for the gaming-ideation decision (re-run).

This is the corrective pass the prior run MISSED. The prior run's PERCEIVE
map explicitly EXCLUDED `discord_bots` (simulator.py metadata / frame), so
FoundryHost (#1, 0.686) was evaluated against Steam/Epic-vs-community WITHOUT
pricing in the incumbent Discord-bot ecosystem that already fills the layer
between platform and volunteer admin.

Facts loaded here (user-verified as authoritative):
  - backup/continuity: Xenon (free), RestoreCord (firewall+analytics),
    Server Maker (credit-metered free tier). Mature, crowded, several free.
  - moderation/anti-abuse: Dyno (4M+ servers, free tier, $4.99/mo), Carl-bot,
    MEE6 ($11.99/mo), Sapphire, YAGPDB, Beemo + Discord's built-in AutoMod
    (buying guides now recommend it BEFORE third-party bots).
  - analytics/member-insight: Orbit, Common Room, Combot, Subo.ai
    (13,000+ communities since 2022).
  - The category is mature enough to HAVE a curated "awesome-discord-growth"
    directory — a signal of a served market, not an invisible unserved one.

Core structural observation: ALL incumbents are SINGLE-SERVER SILOED — Xenon
backs up one server, Dyno moderates one server. NONE carry a member's standing,
trust history, or credentials ACROSS communities or across games. That gap
requires CROSS-COMMUNITY COOPERATION that no single bot vendor has an incentive
to build (each locks a community into its own dashboard; none federate with
competitors). Durable moat = portable community reputation/continuity that
survives moving between servers and games.

Scoring discipline (reuses concepts.py machinery EXACTLY):
  - SAME 8 axes + SAME 1.5x double-weight on moat & resilience.
  - Prior 8 concepts are RE-SCORED downward only where the incumbent set
    directly serves that axis. Where competition does not touch an axis, the
    prior score is UNCHANGED — this isolates the causal effect of loading the
    competitor layer, the whole point of the run.
  - 3 NEW concepts target the genuinely-unserved cross-server whitespace.
"""

from telos.ideation.concepts import AXES, AXIS_WEIGHTS, weighted_score

# ── The incumbent competitor layer (was MISSING from the prior PERCEIVE) ──
COMPETITOR_CLUSTERS = {
    "backup_continuity": [
        "Xenon (free)", "RestoreCord (firewall+analytics, anti-'no restore button')",
        "Server Maker (credit-metered free tier)",
    ],
    "moderation_antiabuse": [
        "Dyno (4M+ servers, free tier, $4.99/mo)",
        "Carl-bot", "MEE6 ($11.99/mo)", "Sapphire", "YAGPDB", "Beemo",
        "Discord AutoMod (platform built-in — now recommended FIRST)",
    ],
    "analytics_member_insight": [
        "Orbit", "Common Room", "Combot", "Subo.ai (13,000+ communities since 2022)",
    ],
    "platform_layer": [
        "Steam", "Epic", "Discord (+ built-in AutoMod)", "volunteer admin + mods",
    ],
    "market_maturity_signal": [
        "'awesome-discord-growth' curated directory exists — category needs a "
        "directory = served, not invisible-unserved.",
    ],
}

# Axis-level competitor pressure (0..1 = fraction of axis value eroded by the
# incumbent set actually serving that dimension). Only applied where incumbents
# directly compete; 0.0 everywhere else.
#   pressure = 0.0 -> untouched by competition
#   pressure → 1.0 -> incumbents fully serve this dimension
COMPETITOR_PRESSURE = {
    "market_size":       0.00,  # market exists; incumbents prove demand (not eroded)
    "feasibility":       0.00,  # buildability unaffected by competition
    "differentiation":   0.00,  # set per-concept below (greatest erosion hits here)
    "data_access":       0.00,
    "user_love":         0.00,
    "monetization":      0.00,
    "moat":              0.00,
    "resilience":        0.00,
}

# Per-concept differentiation + moat erosion from incumbent coverage.
# FoundryHost is the epicenter: EVERY column it sells (backup, moderation,
# analytics) is directly, maturely, often-free served by the bot set.
FOUNDRYHOST = {
    "differentiation": 0.65,  # was 0.65 in prior run; structurally UNIQUE-looking
    "data_access":     0.70,  # was 0.70
    "moat":            0.70,  # was 0.70
    "resilience":      0.75,  # was 0.75
}
# Buyers no longer need a new vendor for any of these; differences are value-add
# on top of a crowded baseline, not a new whitespace.
FOUNDRYHOST_POST_COMPETITION = {
    "differentiation": 0.30,  # 0.65 -> crowded: Xenon/Dyno/MEE6/Orbit all serve these
    "data_access":     0.40,  # 0.70 -> the data is already ingested by incumbents
    "user_love":       0.35,  # 0.60 -> no delta vs. free incumbents + platform AutoMod
    "moat":            0.30,  # 0.70 -> single-server silo = no cross-community wedge
    "resilience":      0.45,  # 0.75 -> "infrastructure is boring" = incumbents win
}

# Re-score map: concept name (short key) -> {axis: post-competition value}.
# Only the axes competition actually erodes are listed; all others carry the
# prior run's value unchanged.
RE_SCORES = {
    "FoundryHost": FOUNDRYHOST_POST_COMPETITION,
    # Other prior concepts are scored with the competitor layer loaded:
    # CareerLedger's provenance data is NOT a Discord-bot function — unchanged
    # but re-examined. SessionBridge's reunion/social graph is not a bot
    # function — unchanged. Their scores stand because competition doesn't
    # serve their axes; differentiation measured vs the bot set is preserved.
}

# ── 3 NEW concepts aimed squarely at the unserved cross-server gap ──
NEW_CONCEPTS = [
    {
        "name": "TrustRail (Portable Cross-Server Reputation & Credential Rail)",
        "insight_key": "asset_provenance + server_community_infra + bot_ecosystem",
        "text": ("A portable trust/credential rail a member carries ACROSS servers "
                 "and games: verified game rank + community standing + honor history "
                 "+ trusted behavior, presented to any server/league/org the member "
                 "joins. The incumbents are single-server silos; TrustRail is the "
                 "cross-server, cross-game identity layer NO single bot vendor can "
                 "incentivize (federation, not lock-in). 'Your reputation follows you.'"),
        "axes": {"market_size": 0.72, "feasibility": 0.40, "differentiation": 0.92,
                 "data_access": 0.86, "user_love": 0.85, "monetization": 0.72,
                 "moat": 0.95, "resilience": 0.82},
        "mvp_validation": ("20 interviews across 3+ game communities: 'what do you "
                           "currently use' BEFORE 'what would you pay for'. Does a "
                           "portable trust badge register? 3 pilot servers of a real "
                           "recent-loss community run a shared reputation layer for "
                           "60 days; measure drama-reports + re-admit conversion."),
        "risk": ("Cold-start: a reputation rail is worthless with zero participating "
                 "servers, and volunteer admins must both trust and share."),
        "mitigation": ("PATTERNED, not one-off: launch as the continuity/backoffice "
                       "bridge between a parent community and its SUCCESSION servers/"
                       "leagues (the 'we lost everything once' event is the wedge), so "
                       "the rail is adopted where identity ALREADY needs to move "
                       "across a boundary — not asking servers to share for no reason. "
                       "The first crossing creates a second, then a network."),
    },
    {
        "name": "FedLayer (Federation Fabric Between Communities)",
        "insight_key": "server_community_infra + bot_ecosystem",
        "text": ("A cooperation fabric between communities: shared trust, ported "
                 "member rolls, and cross-community continuity — the standard layer "
                 "between the bot set and volunteer admin that no dominant vendor "
                 "will build because it federates AWAY from their lock-in dashboard. "
                 "It is the 'mail protocol' for community reputation."),
        "axes": {"market_size": 0.66, "feasibility": 0.35, "differentiation": 0.88,
                 "data_access": 0.85, "user_love": 0.78, "monetization": 0.64,
                 "moat": 0.92, "resilience": 0.80},
        "mvp_validation": ("Interview 15 server owners in interconnected clusters "
                           "(sister servers, league-ladders, successor communities): "
                           "do they want shared trust? Pilot a shared-roll + "
                           "cross-community ban/trust sync across 3 related servers."),
        "risk": ("Adoption chicken: value only appears once MANY servers federate; "
                 "standards are slow and low-visibility."),
        "mitigation": ("PATTERNED: start where the boundary is ALREADY crossed — "
                       "league/sister servers that share members TODAY — so the "
                       "first certificates are exchanged where trust is already "
                       "implicit, codifying an existing behavior instead of asking "
                       "for new trust."),
    },
    {
        "name": "MeritLedger (Game-Agnostic Merit / Trust Ledger)",
        "insight_key": "asset_provenance + cheating_economy",
        "text": ("A neutral, game-agnostic merit/trust ledger that settles the "
                 "'moving between servers AND games' continuity problem: signed "
                 "merit/trust attestations follow the person, not the account or "
                 "the title. The anti-fake property comes from the cheating "
                 "economy itself — the ledger is the rate-limiter the boosters "
                 "cannot economically scale."),
        "axes": {"market_size": 0.68, "feasibility": 0.40, "differentiation": 0.86,
                 "data_access": 0.87, "user_love": 0.80, "monetization": 0.66,
                 "moat": 0.90, "resilience": 0.78},
        "mvp_validation": ("30 interviews: does a verifiable merit attestation reduce "
                           "welcome-trust friction for semi-pro rosters, community "
                           "leagues, mod teams? Pilot 2 game-agnostic leagues sharing "
                           "one merit ledger for one season."),
        "risk": ("Verifiability is only as strong as the weakest issuer; a low-"
                 "quality issuer pollutes trust for all."),
        "mitigation": ("PATTERNED: an issuer-quality economy with reputational "
                       "curation (issuers themselves earn standing), and attestations "
                       "weighted by issuer standing — the ledger self-polices its "
                       "own trust sources, mirroring how the cheating economy is "
                       "rate-limited."),
    },
]


def apply_competitor_pressure(axes: dict, key: str) -> dict:
    """Return a NEW axes dict with the competitor layer priced in.

    For every concept in the prior 8, apply RE_SCORES deltas where present;
    otherwise the prior axes pass through unchanged (isolating competition's
    causal effect). 'key' is the short concept key (e.g. 'FoundryHost').
    """
    out = dict(axes)
    re = RE_SCORES.get(key)
    if re:
        for axis, val in re.items():
            out[axis] = val
    return out


def re_score_all(prior_concepts, prior_keys):
    """Return [(short_key, name, axes, weighted), ...] with competition loaded.

    Args:
        prior_concepts: list of the prior 8 concept dicts (in order).
        prior_keys: list of short keys aligned with prior_concepts.
    """
    results = []
    for c, key in zip(prior_concepts, prior_keys):
        axes = apply_competitor_pressure(c["axes"], key)
        results.append((key, c["name"], axes, weighted_score(axes)))
    return results


def score_new(concept):
    return weighted_score(concept["axes"])

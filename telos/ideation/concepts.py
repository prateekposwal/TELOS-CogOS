"""
Structural Ideation Content — decades-in-gaming vantage.

The PERCEIVE layer's structural reality map and the SIMULATE layer's
candidate futures. Each concept is anchored to the SPECIFIC structural
insight it exploits — not to surface player pain. This is what a
newcomer misses: they see a bot request; a veteran sees a broken
economic structure that a product can sit on.

Scoring axes (EVALUATE):
  market_size      -> 0..1  addressable revenue pool
  feasibility      -> 0..1  buildable in 6-18 months w/ reasonable team
  differentiation  -> 0..1  how structurally unique vs incumbents
  data_access      -> 0..1  can we actually GET the needed data/moat
  user_love        -> 0..1  emotional depth / retention / delight
  monetization     -> 0..1  unit economics + willingness to pay
  moat             -> 0..1  (VETERAN AXIS a) harder to copy as it grows
  fragility        -> 1-x    (VETERAN AXIS b) inverse of single-point dependency
                           (score stored as resilience; higher = LOWER fragility)
"""

# ── PERCEIVE: The structural reality map a veteran sees ──────────────────
STRUCTURAL_INSIGHTS = {
    "platform_take": (
        "Valve/Steam, Epic, Microsoft, Sony take 20-30% of every transaction and "
        "own the storefront, the auth, the wallet, the matchmaking, and the social "
        "graph. Any product that lives purely inside a platform's API is a renter. "
        "The durable value sits in layers the platform does NOT want to build: "
        "cross-platform identity, ownership/provenance, and the secondary economy."
    ),
    "churn_lifecycle": (
        "Live-service games are engineered to churn. Player lifetime value peaks in "
        "the first 30 days then decays along a cliff. The industry practices "
        "'games-as-a-service' but NOBODY owns the cross-game retention layer — "
        "everything is per-title. A player who leaves CS:GO is not a lost customer "
        "to Valve; but to an ecosystem bets on lifetime, they're gold."
    ),
    "cheating_economy": (
        "Anti-cheat is an arms race against a shadow economy that makes real money "
        "(skin laundering, boosters, boost-selling, account theft). Because cheaters "
        "monetize, cheating is not a bug — it's an industry. Trust/credential "
        "infrastructure that is ECONOMICALLY hard to fake is durable, because the "
        "adversary's revenue is the product's reason to exist."
    ),
    "esports_money_flow": (
        "Esports money flows to a thin top (tournament orgs, tier-1 talent) while "
        "the other 99% of ranked players get ladder anxiety, smurfs, and no path. "
        "The amateur/league 'middle class' is unserved: no organized competition, "
        "no credential, no stakes. The orgs/leagues that exist take a cut of a tiny "
        "pie instead of building tiered infrastructure."
    ),
    "asset_provenance": (
        "Skins made Valve billions, but accounts are the real financial instrument: "
        "rank, inventory, game history, legacy. Accounts get stolen, scammed, and "
        "their history is untraceable. The secondary economy beyond skins — the "
        "provenance/career ledger of a gamer — is unbuilt. Everything from hiring "
        "to loaning to verifying a 'pro' requires trusted account history."
    ),
    "dead_game_afterlife": (
        "Games die: servers shut, communities scatter, and a decade of culture "
        "(screenshots, clips, friendships, replays, tournament results) vaporizes. "
        "Preservation is low-margin but the EMOTIONAL hold is enormous and the "
        "churn-handoff ('we played THIS together') is a retention engine the live "
        "industry ignores."
    ),
    "casual_dad_25plus": (
        "The median gamer is 30+, and the fastest-growing, most valuable, least "
        "served cohort is the 25-45 'dad gamer': disposable income, 2-4 hrs/week, "
        "plays to decompress and stay in touch with old friends, can't rank-grind, "
        "won't be griefed, won't buy lootboxes. The industry builds for the 20-year-"
        "old grinder and assumes everyone else is 'casual' — a category error. "
        "This cohort has money and no time; nobody sells them time-respecting "
        "structured play."
    ),
    "server_community_infra": (
        "The real social fabric of gaming is self-hosted servers, community-discord "
        "clusters, private leagues, and modded instances — fragmented, fragile, run "
        "by volunteers, invisible to the platforms that own the top 1% of players. "
        "Community infrastructure (hosting, moderation, credentialing, continuity) "
        "is chronically under-invested because it doesn't fit a storefront model."
    ),
    "streaming_econ": (
        "Streaming concentrates attention on a tiny star tier; the middle creator "
        "earns near-nothing and has no path. Every content tool serves the top. The "
        "under-monetized base is the participation tier. (Prior run touched clips — "
        "we skip that; the structural play is the LEAGUE/ECONOMY underneath, not more "
        "editing software.)"
    ),
}

# ── Weighting: veteran-lens axes get double weight in EVALUATE ───────────
AXES = ["market_size", "feasibility", "differentiation", "data_access",
        "user_love", "monetization", "moat", "resilience"]
AXIS_WEIGHTS = {
    "market_size": 1.0, "feasibility": 1.0, "differentiation": 1.0,
    "data_access": 1.0, "user_love": 1.0, "monetization": 1.0,
    "moat": 1.5,   # veteran axiom (a): structural moat is worth 1.5x
    "resilience": 1.5,  # veteran axiom (b): inverse fragility is worth 1.5x
}


def _c(name, insight_key, text, axes, mvp_validation, risk, mitigation):
    return {
        "name": name,
        "insight_key": insight_key,
        "text": text,
        "axes": axes,
        "mvp_validation": mvp_validation,
        "risk": risk,
        "mitigation": mitigation,
    }


# ── SIMULATE: the candidate futures (8 distinct, structurally out-of-the-box) ──
CONCEPTS = [
    _c(
        "CareerLedger (Account Provenance & Credentialing)",
        "asset_provenance",
        "A verifiable cross-game career/provenance ledger: cryptographically-signed "
        "account history (rank, match results, inventory, era/game legacy) that a "
        "gamer owns and can present to teams, orgs, employers, lenders, and "
        "sweepstakes. 'Verified rank as career currency.' Structural trick: it "
        "sits on the data the platforms ALREADY want to authenticate (matches are "
        "server-authoritative), so it's supply from the games' own trusted outputs "
        "rather than scraping a storefront. It is an identity/credential layer the "
        "platforms won't build because it commoditizes their walled gardens.",
        {"market_size": 0.55, "feasibility": 0.6, "differentiation": 0.85,
         "data_access": 0.6, "user_love": 0.6, "monetization": 0.6,
         "moat": 0.75, "resilience": 0.65},
        "Validate: do 25+ ranked players actually WANT to carry a portable verified "
        "rank out of the game? 20 interviews with dad-gamers + 10 with semi-pros. "
        "Find 1 game title with a sanctioned match-history export; prove a signed "
        "verifiable credential loads without the platform's blessing.",
        "Platforms revoke/deny match data access (the account-provenance tap runs dry).",
        "Patterned mitigation: sign-verifiable credentials FROM each game's own "
        "server-authoritative outputs so the product needs only a ONE-TIME read "
        "hook, then stores an immutable attestation the user holds. Platform "
        "can't claw back what the user owns. Diversify across N titles so no "
        "single API kill.",
    ),
    _c(
        "SessionBridge (Cross-Game Retention / Reunion Layer)",
        "churn_lifecycle",
        "An opt-in social graph + 'SessionBridge' that lets the 25+ casual-dad "
        "cohort convert gaming time into structured reunions: it watches which game "
        "their old friends last played together in, and when 2+ are online in ANY "
        "game it negotiates a 'same-time slot' and drops them into a low-stress, "
        "time-boxed session. It is the cross-title 'we should play again' engine — "
        "the layer above per-title social that NO game owns. Exploits the fact "
        "that engagement is engineered to churn but the RELATIONSHIP is the asset "
        "that persists.",
        {"market_size": 0.7, "feasibility": 0.55, "differentiation": 0.8,
         "data_access": 0.55, "user_love": 0.85, "monetization": 0.55,
         "moat": 0.65, "resilience": 0.55},
        "Validate: do dad-gamers genuinely rehire friends around the past-, not "
        "current-, game? 25 interviews. Validate the network effect thesis: 30+ "
        "churn-behavior data points per user, do they come back at 2x the 30-day "
        "lifeline? Measure cohort retention vs a control.",
        "Presence data is fragmented across Discord/Steam/console — hard to get "
        "cross-title online signals reliably.",
        "Patterned mitigation: start with the ONE signal that is universal and "
        "opt-in (Discord presence + Steam friend list), build the scheduling "
        "layer so the value lives in the REUNION not the presence read — a 'when "
        "shall we' calendar that emails when a match forms. The moat is the "
        "relationship graph + scheduling habit, not the presence probe.",
    ),
    _c(
        "TurfTrust (Anti-Cheat-Adjacent Community Trust Infrastructure)",
        "cheating_economy",
        "Community-level trust scoring that is economically hard to fake — a "
        "'reputation' tiering for players, servers, and mod/admins that survives "
        "account bans and follows the PERSON not the account. Because the cheating "
        "economy monetizes, the defense is the product: run community leagues, "
        "server hosting, and marketplaces through a trust fabric that checks "
        "'is this a 200-hour smurf or a 6,000-hour loyal regular' using behavioral "
        "signals + cross-server history that a paid booster can't cheaply fabricate.",
        {"market_size": 0.6, "feasibility": 0.6, "differentiation": 0.85,
         "data_access": 0.55, "user_love": 0.6, "monetization": 0.6,
         "moat": 0.8, "resilience": 0.7},
        "Validate: does a communal league trust-score actually reduce smurfing/grief "
        "and raise retention vs control? Run 3 real community servers with a "
        "trust overlay + 3 without for 90 days. Measure drama, reports, churn.",
        "Game toers can still farm behavioral trust slowly, and platforms may not "
        "expose the signals needed.",
        "Patterned mitigation: make the trust score VERIFIABLE and TRANSPARENT so "
        "grief over a fake is impossible to hide — the score weights REQUIRE "
        "commitment (longevity, owned-history) that a profit-driven booster "
        "economically cannot scale. It's a rate-limiter on evil, not a lock.",
    ),
    _c(
        "LadderMiddle (Amateur/Public-Legue Infrastructure & Credential)",
        "esports_money_flow",
        "A tiered amateur competition infrastructure for the other 99%: automated "
        "ladder seasons, relegation, clean matchmaking, and a portable 'amateur "
        "ranking' the middle 99% can grind that FEEDS verified signals into "
        "scouting. It flips the esports model — instead of a tiny pro tier "
        "monetizing a small pie, it turns the huge unserved base into a "
        "participation economy with stakes (brackets, seasons, badges, seeds). "
        "Esports money is stuck at the top; this unlocks the middle.",
        {"market_size": 0.7, "feasibility": 0.5, "differentiation": 0.8,
         "data_access": 0.5, "user_love": 0.75, "monetization": 0.6,
         "moat": 0.7, "resilience": 0.5},
        "Validate: do 99th-percentile-amateur players actually grind for a "
        "cross-title amateur rank, or is it ladder-anxiety theater? 30 interviews "
        "with Gold→Diamond players. Validate willingness-to-pay for organized "
        "seasons. Test 1 pilot league with 200 players for 8 weeks; measure "
        "engagement vs matchmaking-only control.",
        "A single platform's matchmaking changes or ToS can fragment the league; "
        "esports organizers defend the top-heavy status quo.",
        "Patterned mitigation: run the LADDER/CREDENTIAL as the product, not the "
        "game — migrate across titles so a season in CS:GO and a season in Dota "
        "both feed one portable amateur ranking. Event organizers are customers; "
        "the ranking is the indivisible asset.",
    ),
    _c(
        "ArchiveLeague (Dead-Game Revival / Community Preservation-as-Service)",
        "dead_game_afterlife",
        "A resurrection+preservation service for canceled/dead games: takes over a "
        "shutting-down title's community, saves the culture (replays, screenshots, "
        "tournament records, friend ties), keeps the servers/mods alive as a "
        "low-cost 'afterlife', and — critically — leverages that preserved history "
        "as a CHURN-HANDOFF asset: when the 'forever game' dies, the community "
        "doesn't scatter; it moves wholesale, taking its emotional ledger with it.",
        {"market_size": 0.45, "feasibility": 0.7, "differentiation": 0.8,
         "data_access": 0.75, "user_love": 0.8, "monetization": 0.45,
         "moat": 0.6, "resilience": 0.75},
        "Validate: is the emotional pull real enough to pay? 20 dead-game community "
        "leaders — would they fund a memorial/preservation tier? Measure how much "
        "of a dead game's community would move to a successor title if it carried "
        "their history.",
        "Copyright/licensing: publishers can shut down unauthorized revival, and "
        "users may not value preservation enough to pay.",
        "Patterned mitigation: license properly + focus on the LOW-risk, HIGH-"
        "value 'history ledger' (the user's OWN screenshots/replays/records are "
        "theirs) rather than re-hosting the game binary; partner with publishers "
        "as a preservation vendor when the title EOLs. The carry-forward identity "
        "is the product, not the server.",
    ),
    _c(
        "AFKHaven (The 25+ Casual-Dad Gaming OS)",
        "casual_dad_25plus",
        "A structured, time-respecting play layer for the 25-45 dad / adult gamer: "
        "auto-scheduling, anti-grief matchmaking floors, 'I have 40 minutes' "
        "session templates, and a curated catalog of high-ROI short-session games "
        "— presented as a calm OS over the chaotic storefront. It treats the "
        "adult gamer as a first-class market with money and no time, not as a "
        "lesser 'casual'.",
        {"market_size": 0.8, "feasibility": 0.6, "differentiation": 0.75,
         "data_access": 0.6, "user_love": 0.85, "monetization": 0.65,
         "moat": 0.55, "resilience": 0.7},
        "Validate: does a time-boxed, structured session reduce adult churn vs "
        "open-ended play? 30 interviews with 25+ gamers; beta with 100 late-"
        "20s/30s players; measure 60-day retention and weekly play-count per hour.",
        "Retention-benefit is real only if the user stays in the ecosystem; could "
        "be a nicer wrapper with thin defensibility.",
        "Patterned mitigation: build the defensible core as the SCHEDULING + "
        "social-reunion moat (SessionBridge's graph) so the 'OS' is the front for "
        "a relationship+time asset that compounds; curate-not-own the game catalog "
        "so no single title dependency. This pairs as the UX for SessionBridge.",
    ),
    _c(
        "FoundryHost (Community Server / League Infrastructure-as-a-Service)",
        "server_community_infra",
        "Managed infrastructure for the invisible 99% — community servers, discord "
        "clusters, private leagues, modded instances — sold as a turnkey 'community "
        "operating system': hosting, anti-abuse moderation, credentialed member "
        "rolls, scheduler, and continuity backup so a community survives server "
        "death. Exploits the reality that community infra is fragmented and "
        "volunteer-run and invisible to storefronts.",
        {"market_size": 0.6, "feasibility": 0.75, "differentiation": 0.65,
         "data_access": 0.7, "user_love": 0.6, "monetization": 0.7,
         "moat": 0.7, "resilience": 0.75},
        "Validate: do volunteer community admins PAY for managed infra, or do "
        "they keep DIYing? 20 server owners. Test willingness-to-pay of a "
        "$5-15/mo 'community keep-alive' tier. Pilot 3 communities for 60 days.",
        "Volunteer communities are price-sensitive and may reject centralized "
        "management as 'taking over.'",
        "Patterned mitigation: sell the pain-lowering BACKOFFICE (backups, "
        "moderation, continuity) not ownership — a server admin who hates "
        "resetting the box every week becomes the champion. Seed via communities "
        "that already lost data; the 'we lost everything once' story converts.",
    ),
    _c(
        "KarmaCap (Secondary-Economy Trust Layer; the 'FairPlay Score')",
        "cheating_economy",
        "A trust/verification layer for the secondary account/skin economy: age-"
        "verified, behavior-weighted 'FairPlay' scores that marketplaces, "
        "boosters, account-sellers, and tournament orgs use to reduce scams and "
        "chargebacks. Because the secondary economy is unregulated and fraud-"
        "riddled, a trusted settlement/verification rail is the toll).",
        {"market_size": 0.65, "feasibility": 0.5, "differentiation": 0.8,
         "data_access": 0.5, "user_love": 0.55, "monetization": 0.8,
         "moat": 0.7, "resilience": 0.6},
        "Validate: does a verified-fairplay signal reduce marketplace fraud and "
        "raise seller prices/he match? Partner with 2 marketplaces to A/B a "
        "verified badge; measure conversion + dispute rate. 20 scam-victim "
        "interviews.",
        "Gray-market regulatory/legal exposure; marketplaces may not adopt or "
        "could bypass.",
        "Patterned mitigation: be the NEUTRAL clearing trust both buyers and "
        "sellers need (a two-sided network effect the scammers can't fake); "
        "position as damage-reduction not policing, so it's adopted by "
        "marketplaces as a conversion tool, and stay platform-agnostic to ride "
        "any storefront.",
    ),
]



def weighted_score(axes):
    """EVALUATE: veteran-weighted composite (moat + resilience at 1.5x).

    Args:
        axes: dict of 8 axis scores (same keys as AXES).
    """
    num = sum(AXIS_WEIGHTS[a] * axes[a] for a in AXES)
    den = sum(AXIS_WEIGHTS.values())
    return num / den

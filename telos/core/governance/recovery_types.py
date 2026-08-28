"""Canonical intent-type sets shared by recovery/stagnation machinery and the
council's evidence advisor (Λ6.5 — ONE canonical source, never two divergent
lists that drift apart).

The operative rule these encode: a GOVERNANCE-SUPPRESSED outcome (action
vetoed before it could be tested) is NOT evidence — not about the intent
type, not about the approach, not about the world.
"""

# Inquiry/dwell types: deliberate exploration — stagnation arming must NOT
# force-escape these (their dwell IS the inquiry; the firewall owns their
# action_loop escape path).
STAGNATION_EXEMPT_INQUIRY_TYPES = frozenset({
    "inquiry", "inquiry_explore", "inquiry_recalibrate", "inquiry_resolve",
    "curiosity_explore", "perceive", "memory_miss", "blended_inquiry",
})

# Designed escape/recovery types: they ARE the answer to falsification —
# stagnation never re-arms on them, and the evidence advisor never scores
# them falsified. A recovery intent is the system ACTING to escape; counting
# its suppressed attempts as its own falsification is misattribution.
STAGNATION_EXEMPT_RECOVERY_TYPES = frozenset({
    "goal_seek_recovery",
})

# Failure classifications that mean "governance suppressed the action before
# it could be tested" — not "the approach failed". Both the failure-ledger
# path and the KnowledgeGraph path of MemoryAdvisor filter on these, so a
# vetoed attempt can never poison the approach-failure space.
GOVERNANCE_SUPPRESSION_REASONS = frozenset({
    "governance_intervention",
    "simulation_divergence",
})

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

# Failure classifications that mean the recorded outcome NEVER TESTED the
# approach, so it is NOT evidence that the approach failed. This is the
# MemoryAdvisor's evidence filter — BOTH its FailureLedger path and its
# KnowledgeGraph path. It is a superset of GOVERNANCE_SUPPRESSION_REASONS:
#   * governance suppression — the action was vetoed before it could run;
#   * advisory escalation   — `unresolved_uncertainty` is an uncertainty
#     signal ("seek clarity"), not a measured approach falsification. A cycle
#     the council ESCALATED (advisory, default proceeds) was never a test of
#     the approach's efficacy, so recording it as an approach failure and then
#     citing it as a structural barrier is the same misattribution as counting
#     a suppression. NOTE: the memory controller's poison gate keeps using the
#     narrower GOVERNANCE_SUPPRESSION_REASONS — an escalation is not a
#     governance suppression.
NOT_EVIDENCE_APPROACH_FAILURE_REASONS = GOVERNANCE_SUPPRESSION_REASONS | frozenset({
    "unresolved_uncertainty",
})

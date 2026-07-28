"""
PatternLibrary — Cross-Domain Knowledge Transfer (Λ4.7 System Memory)

Patterns are domain-independent signatures extracted from decision cycles.
They enable the system to recognize "I've seen this situation before" even
when the domain changes — enabling cross-domain transfer.

Architecture:
  PatternSignature: stable hash of state + intent features
  Pattern:          a recorded cycle snapshot (sig, action, outcome, domain)
  PatternLibrary:   stores, matches, and retrieves patterns across domains

Cross-domain matching works by comparing pattern signatures, not domain
labels. If two different domains produce similar state/intent signatures,
the library recommends the known approach from the other domain.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
import time
import hashlib
import logging
import numpy as np
from collections import defaultdict

logger = logging.getLogger('telos_pattern')


class PatternType(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    COUNCIL_BLOCK = "council_block"
    HIGH_DRIFT = "high_drift"
    LOW_INTEGRITY = "low_integrity"
    ESCALATION = "escalation"
    RECOVERY = "recovery"


@dataclass
class PatternSignature:
    """Domain-independent fingerprint of a decision cycle.

    The signature is a hash of the state vector, selected intent type,
    and mission drift — all domain-agnostic quantities.
    """
    state_hash: str
    intent_type: str
    drift_bucket: str       # "low", "medium", "high"
    integrity_bucket: str   # "low", "medium", "high"
    action_signature: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_feature_vector(self) -> np.ndarray:
        """Convert to a compact feature vector for similarity search.

        Returns a unit-normalized vector with one-hot encoded category
        features and hashed continuous features for discriminating
        similarity across domains.
        """
        drift_map = {"low": 0, "medium": 1, "high": 2}
        integ_map = {"low": 0, "medium": 1, "high": 2}
        intent_val = int(hashlib.md5(self.intent_type.encode()).hexdigest()[:4], 16) / 65535.0
        action_val = int(hashlib.md5(self.action_signature.encode()).hexdigest()[:4], 16) / 65535.0 if self.action_signature else 0.0
        d_idx = drift_map.get(self.drift_bucket, 1)
        i_idx = integ_map.get(self.integrity_bucket, 1)
        vec = np.zeros(10, dtype=np.float32)
        vec[d_idx] = 1.0
        vec[3 + i_idx] = 1.0
        vec[6] = intent_val
        vec[7] = action_val
        vec[8] = float(len(self.state_hash)) / 64.0 if self.state_hash else 0.0
        vec[9] = 1.0
        norm = float(np.linalg.norm(vec))
        return vec / norm if norm > 1e-9 else vec


@dataclass
class Pattern:
    """A stored decision-cycle pattern for cross-domain reference."""
    pattern_id: str
    pattern_type: PatternType
    domain: str
    signature: PatternSignature
    action_taken: Optional[str]
    outcome_score: float
    timestamp: float = 0.0
    match_count: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)


class PatternLibrary:
    """Cross-domain pattern storage and matching engine.

    Stores patterns by their domain-independent signature, not by domain
    label. Enables cross-domain transfer: a pattern learned in domain A
    can be matched against a similar state in domain B.

    Similarity is computed via cosine similarity of feature vectors.
    """

    def __init__(self, max_patterns: int = 200, similarity_threshold: float = 0.75):
        self._patterns: Dict[str, Pattern] = {}
        self._domain_index: Dict[str, List[str]] = {}
        self._type_index: Dict[PatternType, List[str]] = {}
        self._feature_vectors: Dict[str, np.ndarray] = {}
        self._max_patterns = max_patterns
        self._similarity_threshold = similarity_threshold
        self._cycle = 0

    def record(self, domain: str, pattern_type: PatternType,
               signature: PatternSignature, action_taken: Optional[str] = None,
               outcome_score: float = 0.5,
               metadata: Optional[Dict] = None) -> str:
        """Store a pattern. Deduplicates exact (domain, type, intent, drift, integrity) matches."""
        existing = self._find_exact_match(domain, pattern_type, signature)
        if existing:
            pat = self._patterns[existing]
            pat.match_count += 1
            pat.outcome_score = 0.7 * pat.outcome_score + 0.3 * outcome_score
            pat.timestamp = time.time()
            return pat.pattern_id

        pattern_id = f"pat_{hashlib.md5(f'{domain}{time.time()}'.encode()).hexdigest()[:8]}"
        pat = Pattern(
            pattern_id=pattern_id,
            pattern_type=pattern_type,
            domain=domain,
            signature=signature,
            action_taken=action_taken,
            outcome_score=outcome_score,
            timestamp=time.time(),
            metadata=metadata or {},
        )

        self._patterns[pattern_id] = pat
        self._feature_vectors[pattern_id] = signature.to_feature_vector()
        self._domain_index.setdefault(domain, []).append(pattern_id)
        self._type_index.setdefault(pattern_type, []).append(pattern_id)

        if len(self._patterns) > self._max_patterns:
            oldest = min(self._patterns, key=lambda pid: self._patterns[pid].timestamp)
            self._remove(oldest)

        logger.debug(f"PatternLibrary: recorded {pattern_type} in '{domain}' ({pattern_id})")
        return pattern_id

    def query(self, signature: PatternSignature,
              domain: Optional[str] = None,
              top_k: int = 5) -> List[Tuple[Pattern, float]]:
        """Find patterns matching this signature, optionally filtered by domain.

        Returns list of (Pattern, similarity_score) sorted by similarity descending.
        """
        candidates = self._feature_vectors
        if domain:
            pids = self._domain_index.get(domain, [])
            candidates = {pid: self._feature_vectors.get(pid) for pid in pids
                          if pid in self._feature_vectors}

        if not candidates:
            return []

        query_vec = signature.to_feature_vector()
        scored: List[Tuple[str, float]] = []
        for pid, vec in candidates.items():
            sim = self._cosine_similarity(query_vec, vec)
            if sim >= self._similarity_threshold:
                scored.append((pid, sim))

        scored.sort(key=lambda x: -x[1])
        return [(self._patterns[pid], sim) for pid, sim in scored[:top_k]]

    def cross_domain_query(self, signature: PatternSignature,
                           exclude_domain: str,
                           top_k: int = 3) -> List[Tuple[Pattern, float]]:
        """Find similar patterns from OTHER domains (cross-domain transfer).

        This is the core cross-domain transfer method: given a signature
        from domain A, find matching patterns from domains B, C, D...
        """
        candidates = {}
        for domain, pids in self._domain_index.items():
            if domain == exclude_domain:
                continue
            for pid in pids:
                if pid in self._feature_vectors:
                    candidates[pid] = self._feature_vectors[pid]

        if not candidates:
            return []

        query_vec = signature.to_feature_vector()
        scored: List[Tuple[str, float]] = []
        for pid, vec in candidates.items():
            sim = self._cosine_similarity(query_vec, vec)
            if sim >= self._similarity_threshold:
                scored.append((pid, sim))

        scored.sort(key=lambda x: -x[1])
        return [(self._patterns[pid], sim) for pid, sim in scored[:top_k]]

    def get_patterns_by_type(self, pattern_type: PatternType) -> List[Pattern]:
        return [self._patterns[pid] for pid in self._type_index.get(pattern_type, [])
                if pid in self._patterns]

    def get_domain_summary(self, domain: str) -> Dict:
        pids = self._domain_index.get(domain, [])
        patterns = [self._patterns[pid] for pid in pids if pid in self._patterns]
        return {
            "domain": domain,
            "total_patterns": len(patterns),
            "by_type": {
                t.value: sum(1 for p in patterns if p.pattern_type == t)
                for t in PatternType
            },
            "avg_outcome": float(np.mean([p.outcome_score for p in patterns])) if patterns else 0.0,
        }

    def stats(self) -> Dict:
        return {
            "total_patterns": len(self._patterns),
            "domains": list(self._domain_index.keys()),
            "by_type": {
                t.value: len(self._type_index.get(t, []))
                for t in PatternType
            },
        }

    @staticmethod
    def signature_from_decision(di: float, md: float, intent_type: str,
                                 action_signature: str = "",
                                 state_hash: str = "") -> PatternSignature:
        """Build a PatternSignature from raw decision metrics."""
        drift_bucket = "low" if md < 1.0 else ("medium" if md < 3.0 else "high")
        integrity_bucket = "high" if di > 0.8 else ("medium" if di > 0.5 else "low")
        return PatternSignature(
            state_hash=state_hash or str(time.time()),
            intent_type=intent_type,
            drift_bucket=drift_bucket,
            integrity_bucket=integrity_bucket,
            action_signature=action_signature,
        )

    def _remove(self, pattern_id: str) -> None:
        pat = self._patterns.pop(pattern_id, None)
        self._feature_vectors.pop(pattern_id, None)
        if pat:
            domain_list = self._domain_index.get(pat.domain, [])
            if pattern_id in domain_list:
                domain_list.remove(pattern_id)
            type_list = self._type_index.get(pat.pattern_type, [])
            if pattern_id in type_list:
                type_list.remove(pattern_id)

    def _find_exact_match(self, domain: str, pattern_type: PatternType,
                           signature: PatternSignature) -> Optional[str]:
        """Find a pattern that matches on domain, type, and all signature fields."""
        key = (domain, pattern_type, signature.intent_type,
               signature.drift_bucket, signature.integrity_bucket)
        for pid, pat in self._patterns.items():
            s = pat.signature
            if (pat.domain == domain and pat.pattern_type == pattern_type
                    and s.intent_type == signature.intent_type
                    and s.drift_bucket == signature.drift_bucket
                    and s.integrity_bucket == signature.integrity_bucket):
                return pid
        return None

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        norm = float(np.linalg.norm(a) * np.linalg.norm(b))
        return float(np.dot(a, b) / norm) if norm > 1e-9 else 0.0


    def save(self, path: str) -> None:
        """Persist the PatternLibrary to a JSON file."""
        import json
        data = {
            "patterns": {
                pid: {
                    "pattern_id": p.pattern_id,
                    "pattern_type": p.pattern_type.value,
                    "domain": p.domain,
                    "signature": {
                        "state_hash": p.signature.state_hash,
                        "intent_type": p.signature.intent_type,
                        "drift_bucket": p.signature.drift_bucket,
                        "integrity_bucket": p.signature.integrity_bucket,
                        "action_signature": p.signature.action_signature,
                    },
                    "action_taken": p.action_taken,
                    "outcome_score": p.outcome_score,
                    "timestamp": p.timestamp,
                    "match_count": p.match_count,
                    "metadata": p.metadata,
                }
                for pid, p in self._patterns.items()
            },
            "domain_index": {d: pids for d, pids in self._domain_index.items()},
            "type_index": {t.value: pids for t, pids in self._type_index.items()},
            "similarity_threshold": self._similarity_threshold,
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        logger.debug(f"PatternLibrary: saved {len(self._patterns)} patterns to {path}")

    def load(self, path: str) -> None:
        """Restore the PatternLibrary from a JSON file."""
        import json
        try:
            with open(path) as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logger.debug(f"PatternLibrary: no checkpoint at {path}")
            return

        for pid, pd in data.get("patterns", {}).items():
            sig = PatternSignature(
                state_hash=pd["signature"]["state_hash"],
                intent_type=pd["signature"]["intent_type"],
                drift_bucket=pd["signature"]["drift_bucket"],
                integrity_bucket=pd["signature"]["integrity_bucket"],
                action_signature=pd["signature"].get("action_signature", ""),
            )
            pat = Pattern(
                pattern_id=pid,
                pattern_type=PatternType(pd["pattern_type"]),
                domain=pd["domain"],
                signature=sig,
                action_taken=pd.get("action_taken"),
                outcome_score=pd["outcome_score"],
                timestamp=pd.get("timestamp", 0.0),
                match_count=pd.get("match_count", 1),
                metadata=pd.get("metadata", {}),
            )
            self._patterns[pid] = pat
            self._feature_vectors[pid] = sig.to_feature_vector()
        self._domain_index = defaultdict(set, {
            d: set(pids) for d, pids in data.get("domain_index", {}).items()
        })
        self._type_index = {
            PatternType(t): set(pids)
            for t, pids in data.get("type_index", {}).items()
        }
        logger.info(f"PatternLibrary: loaded {len(self._patterns)} patterns from {path}")



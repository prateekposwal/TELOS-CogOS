"""
IdentityCompression — Compress Many Experiences Into One Principle.

Prateek's insight: "Identity compression — compress 100 conversations into
one principle, one belief, one identity update. Identity emerges from
compression, not accumulation."

Most systems accumulate experiences without compressing them into identity.
Identity Compression distills many observations into core principles. Instead
of storing 100 conversations, it extracts the single principle that explains
all of them. Identity is what remains after compression, not what accumulates.

Key insight: If you have 100 experiences that all point to the same principle,
storing 100 traces is wasteful. Store the principle. Identity = compression.

Architecture:
  - Experience Stream: incoming observations tagged with context
  - Compression Engine: batch processes experiences into patterns
  - Principle Extraction: identifies recurring themes and values
  - Identity Update: principles become identity markers with confidence
  - Compression Ratio: how many experiences were compressed into each principle

Compression pipeline:
  Experience Cluster → Pattern Recognition → Principle Formulation →
  Identity Marker Integration → Confidence Assignment → Storage

Example:
  - 50 experiences of "user prefers concise answers"
  - 30 experiences of "user values accuracy over speed"
  - 20 experiences of "user appreciates follow-up questions"
  → Principle: "User values concise accuracy with interactive refinement"
  → Identity marker: "attentive_precision"
"""

from __future__ import annotations

import logging
import time
import math
import hashlib
import numpy as np
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum

logger = logging.getLogger('telos_identity_compression')


class CompressionLevel(Enum):
    RAW = "raw"                    # No compression — individual experiences
    CLUSTER = "cluster"            # Grouped by similarity
    PATTERN = "pattern"            # Recurring theme extracted
    PRINCIPLE = "principle"        # Abstracted rule/guideline
    IDENTITY = "identity"          # Integrated into core identity marker


@dataclass
class ExperienceTag:
    """Metadata tag for an experience."""
    source: str
    confidence: float
    context_hash: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class Principle:
    """A compressed principle extracted from many experiences."""
    id: str
    description: str
    compression_ratio: float       # experiences_compressed / 1
    experiences_compressed: int
    confidence: float              # How confident we are in this principle
    markers_generated: List[str]   # Identity markers derived from this principle
    first_extracted: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)
    evidence_keys: List[str] = field(default_factory=list)  # Keys of supporting experiences

    @property
    def compression_efficiency(self) -> float:
        """How efficient was this compression? Higher = better."""
        if self.experiences_compressed <= 1:
            return 0.0
        return (1.0 - 1.0 / self.experiences_compressed) * self.confidence


@dataclass
class CompressionReport:
    """Report of a compression cycle."""
    cycle: int
    experiences_input: int
    principles_extracted: int
    markers_generated: List[str]
    compression_rate: float        # input / output ratio
    identity_delta: Dict[str, Any]


class IdentityCompression:
    """Compresses many experiences into core identity principles.

    The compressor:
    1. Receives tagged experiences from the pipeline
    2. Batches experiences when enough accumulate
    3. Clusters by theme, source, and context
    4. Extracts principles that summarize clusters
    5. Generates identity markers from principles
    6. Reports compression metrics

    NOT the same as:
      - ExperienceManager (stores full traces for learning)
      - SkillLibrary (indexes successful procedures)
      - SystemSelf identity markers (which this module FEEDS)

    This module is the IDENTITY DISTILLERY: it extracts essence from volume.
    """

    def __init__(self, batch_size: int = 20,
                 similarity_threshold: float = 0.6,
                 min_compression_ratio: float = 3.0):
        self._batch_size = batch_size
        self._similarity_threshold = similarity_threshold
        self._min_compression_ratio = min_compression_ratio

        # Experience buffer (waiting for compression)
        self._experience_buffer: List[Dict] = []

        # Compressed principles
        self._principles: Dict[str, Principle] = {}

        # Generated identity markers and their provenance
        self._identity_markers: Dict[str, Dict] = {}

        # Compression history
        self._reports: List[CompressionReport] = []
        self._max_reports = 100

        # Stats
        self._total_experiences_received: int = 0
        self._total_experiences_compressed: int = 0
        self._total_principles_extracted: int = 0
        self._total_compression_cycles: int = 0

    def add_experience(self, description: str, source: str,
                        context: Optional[Dict] = None,
                        confidence: float = 0.5) -> None:
        """Add a new experience to the compression buffer.

        Args:
            description: What happened or was learned
            source: Where this came from (stream, council, user_feedback, etc.)
            context: Surrounding context (state, goals, outcome)
            confidence: How reliable this experience is
        """
        self._experience_buffer.append({
            "description": description,
            "source": source,
            "context": context or {},
            "confidence": confidence,
            "timestamp": time.time(),
        })
        self._total_experiences_received += 1

        # Check if buffer is ready for compression
        if len(self._experience_buffer) >= self._batch_size:
            self.compress()

    def compress(self) -> Optional[CompressionReport]:
        """Run compression on the experience buffer.

        Returns:
            CompressionReport with results, or None if buffer too small
        """
        if len(self._experience_buffer) < max(3, self._batch_size * 0.5):
            return None

        buffer = self._experience_buffer[:]
        self._experience_buffer = []
        n_input = len(buffer)

        # Cluster experiences by source and keyword similarity
        clusters = self._cluster_experiences(buffer)

        # Extract principles from clusters
        new_principles: List[Principle] = []
        new_markers: List[str] = []

        for cluster_key, cluster in clusters.items():
            if len(cluster) < 3:
                continue  # Too few to compress meaningfully

            # Extract principle description (simplified — in production use LLM)
            principle_desc = self._extract_principle(cluster, cluster_key)
            if not principle_desc:
                continue

            # Generate identity markers from the principle
            markers = self._generate_markers(principle_desc, cluster_key)

            # Create or update principle
            pkey = hashlib.md5(principle_desc.encode()).hexdigest()[:12]
            if pkey in self._principles:
                # Update existing principle
                existing = self._principles[pkey]
                existing.experiences_compressed += len(cluster)
                existing.confidence = min(1.0, existing.confidence + 0.05)
                existing.last_updated = time.time()
                existing.compression_ratio = existing.experiences_compressed / 1.0
                # Add new markers
                for m in markers:
                    if m not in existing.markers_generated:
                        existing.markers_generated.append(m)
                        new_markers.append(m)
            else:
                # New principle
                principle = Principle(
                    id=f"principle_{pkey}",
                    description=principle_desc,
                    compression_ratio=len(cluster),
                    experiences_compressed=len(cluster),
                    confidence=min(0.8, 0.3 + len(cluster) * 0.02),
                    markers_generated=markers,
                    evidence_keys=[f"exp_{int(e['timestamp']*1000)}" for e in cluster],
                )
                self._principles[pkey] = principle
                new_principles.append(principle)
                new_markers.extend(markers)

            # Register identity markers
            for marker in markers:
                if marker not in self._identity_markers:
                    self._identity_markers[marker] = {
                        "source_principles": [],
                        "first_generated": time.time(),
                        "strength": 0.3,
                        "experience_count": 0,
                    }
                self._identity_markers[marker]["source_principles"].append(pkey)
                self._identity_markers[marker]["experience_count"] += len(cluster)
                self._identity_markers[marker]["strength"] = min(1.0,
                    self._identity_markers[marker]["strength"] + 0.05)

        self._total_experiences_compressed += n_input
        self._total_compression_cycles += 1
        self._total_principles_extracted += len(new_principles)

        # Compute compression rate
        compression_rate = n_input / max(len(new_principles), 1)

        report = CompressionReport(
            cycle=self._total_compression_cycles,
            experiences_input=n_input,
            principles_extracted=len(new_principles),
            markers_generated=new_markers,
            compression_rate=compression_rate,
            identity_delta={
                "new_principles": len(new_principles),
                "new_markers": new_markers,
                "updated_principles": len(self._principles),
            },
        )

        self._reports.append(report)
        if len(self._reports) > self._max_reports:
            self._reports.pop(0)

        if new_principles:
            logger.info(
                f"IdentityCompression: compressed {n_input} experiences → "
                f"{len(new_principles)} principles, {len(new_markers)} markers "
                f"(rate: {compression_rate:.1f}x)"
            )

        return report

    def _cluster_experiences(self, buffer: List[Dict]) -> Dict[str, List[Dict]]:
        """Cluster experiences by source and semantic keywords.
            Args:
                buffer: the buffer argument for this call.
        """
        clusters: Dict[str, List[Dict]] = defaultdict(list)

        for exp in buffer:
            source = exp.get('source', 'unknown')
            desc = exp.get('description', '').lower()

            # Extract key terms as cluster signature
            # In production: use embedding similarity
            # Here: use source + topic words
            topic_words = [w for w in desc.split() if len(w) > 4][:3]
            cluster_key = f"{source}:{' '.join(topic_words)}" if topic_words else source

            clusters[cluster_key].append(exp)

        return clusters

    def _extract_principle(self, cluster: List[Dict],
                            cluster_key: str) -> Optional[str]:
        """Extract a principle from a cluster of experiences.

        In production, this would use an LLM or NLP summarization.
        Here we use a keyword-based extraction.
        Args:
            cluster_key: the cluster_key argument for this call.
        """
        if not cluster:
            return None

        # Collect all descriptions
        descriptions = [e.get('description', '') for e in cluster]
        sources = {e.get('source', 'unknown') for e in cluster}

        # Find most common significant words
        word_freq: Dict[str, int] = defaultdict(int)
        for desc in descriptions:
            words = desc.lower().split()
            for w in words:
                if len(w) > 4:
                    word_freq[w] += 1

        # Top words form the principle
        top_words = sorted(word_freq, key=word_freq.get, reverse=True)[:5]
        if not top_words:
            return None

        source_str = ', '.join(sorted(sources))
        principle = (f"Across {len(cluster)} experiences from {source_str}: "
                    f"key themes include {', '.join(top_words)}")

        return principle

    def _generate_markers(self, principle_desc: str, cluster_key: str) -> List[str]:
        """Generate identity markers from a principle.

        Markers are short, reusable tags that encode identity-relevant traits.
        Args:
            principle_desc: the principle_desc argument for this call.
            cluster_key: the cluster_key argument for this call.
        """
        words = principle_desc.lower().split()
        # Extract meaningful words as marker candidates
        candidates = [w.strip('.,:;!?()[]') for w in words
                     if len(w) > 4 and w not in ('across', 'experiences', 'include', 'from')]
        # Deduplicate and limit
        seen: Set[str] = set()
        markers = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                markers.append(c)
            if len(markers) >= 3:
                break

        return markers or ["compressed_insight"]

    def get_top_principles(self, top_n: int = 5) -> List[Principle]:
        """Get principles sorted by compression efficiency.
            Args:
                top_n: the top_n argument for this call.
        """
        sorted_principles = sorted(
            self._principles.values(),
            key=lambda p: p.compression_efficiency,
            reverse=True,
        )
        return sorted_principles[:top_n]

    def get_identity_markers(self) -> Dict[str, float]:
        """Get all identity markers with their current strength."""
        return {
            marker: info['strength']
            for marker, info in self._identity_markers.items()
        }

    @property
    def total_experiences(self) -> int:
        return self._total_experiences_received

    @property
    def total_principles(self) -> int:
        return len(self._principles)

    @property
    def overall_compression_rate(self) -> float:
        if self._total_principles_extracted == 0:
            return 0.0
        return self._total_experiences_compressed / self._total_principles_extracted

    @property
    def buffer_size(self) -> int:
        return len(self._experience_buffer)

    def to_dict(self) -> Dict:
        return {
            "total_experiences_received": self._total_experiences_received,
            "total_experiences_compressed": self._total_experiences_compressed,
            "total_principles_extracted": self._total_principles_extracted,
            "total_compression_cycles": self._total_compression_cycles,
            "overall_compression_rate": round(self.overall_compression_rate, 1),
            "buffer_size": self.buffer_size,
            "principles": [
                {
                    "id": p.id[:16],
                    "description": p.description[:60],
                    "experiences_compressed": p.experiences_compressed,
                    "confidence": round(p.confidence, 3),
                    "compression_efficiency": round(p.compression_efficiency, 3),
                    "markers": p.markers_generated,
                }
                for p in self.get_top_principles(10)
            ],
            "identity_markers": self.get_identity_markers(),
            "recent_compressions": [
                {
                    "cycle": r.cycle,
                    "input": r.experiences_input,
                    "principles": r.principles_extracted,
                    "markers": r.markers_generated,
                    "compression_rate": round(r.compression_rate, 1),
                }
                for r in self._reports[-5:]
            ],
        }

"""
Honest contract tests for telos/core/identity/identity_compression.py
(IdentityCompression, Principle, CompressionLevel, CompressionReport).

Compressor behavior (read from source):
  - compress() runs only when len(buffer) >= max(3, batch_size*0.5).
  - add_experience() auto-compresses when len(buffer) reaches batch_size.
  - Experiences are clustered by source + first 3 topic words (len>4).
  - A principle is only formed from a cluster of >= 3 experiences.
"""

import pytest

from telos.core.identity.identity_compression import (
    CompressionLevel,
    CompressionReport,
    ExperienceTag,
    IdentityCompression,
    Principle,
)


def test_compression_level_enum_values():
    assert CompressionLevel.RAW.value == "raw"
    assert CompressionLevel.CLUSTER.value == "cluster"
    assert CompressionLevel.PATTERN.value == "pattern"
    assert CompressionLevel.PRINCIPLE.value == "principle"
    assert CompressionLevel.IDENTITY.value == "identity"


def test_compress_returns_none_below_threshold():
    # batch_size=10 -> threshold max(3, 5)=5. 3 experiences < 5 -> None.
    compressor = IdentityCompression(batch_size=10)
    for _ in range(3):
        compressor.add_experience("user prefers concise answers", "user_feedback")
    assert compressor.compress() is None
    assert compressor.total_principles == 0
    assert compressor.buffer_size == 3


def test_buffer_auto_compresses_when_batch_full():
    compressor = IdentityCompression(batch_size=5)
    for i in range(5):
        compressor.add_experience(f"user values precise feedback {i}", "feedback")
    # Auto-triggered upon reaching batch_size.
    assert compressor.buffer_size == 0
    assert compressor._total_compression_cycles >= 1


def test_compress_reports_compression_metrics():
    # batch_size=100, so threshold = max(3, 50) = 50 -> use 50+ experiences.
    compressor = IdentityCompression(batch_size=100)
    for i in range(60):
        compressor.add_experience(f"agent always prefers precision metric {i}",
                                  "measurement")
    report = compressor.compress()
    assert isinstance(report, CompressionReport)
    assert report.experiences_input == 60
    assert report.cycle == 1
    assert report.identity_delta["new_principles"] >= 1
    assert report.compression_rate > 0
    assert compressor.total_principles >= 1


def test_principle_compression_efficiency():
    single = Principle(
        id="p1", description="d",
        compression_ratio=1.0, experiences_compressed=1,
        confidence=0.5, markers_generated=["m"],
    )
    assert single.compression_efficiency == 0.0

    many = Principle(
        id="p2", description="d",
        compression_ratio=10.0, experiences_compressed=10,
        confidence=0.8, markers_generated=["m"],
    )
    expected = (1.0 - 1.0 / 10) * 0.8
    assert many.compression_efficiency == pytest.approx(expected)


def test_identity_markers_generated_from_principle():
    compressor = IdentityCompression(batch_size=100)
    for i in range(60):
        compressor.add_experience("user consistently values honest reporting clarity",
                                  "council")
    compressor.compress()
    markers = compressor.get_identity_markers()
    assert len(markers) >= 1
    for strength in markers.values():
        assert 0.0 <= strength <= 1.0


def test_marker_strength_bounded_at_1():
    compressor = IdentityCompression(batch_size=400)
    for i in range(300):
        compressor.add_experience("repeat same theme repeated often", "stream")
    report = compressor.compress()
    assert report is not None
    for strength in compressor.get_identity_markers().values():
        assert strength <= 1.0


def test_top_principles_sorted_by_efficiency():
    compressor = IdentityCompression(batch_size=200)
    # Two distinct source+keyword clusters of differing sizes. Total (120)
    # exceeds the compress threshold of max(3, 100)=100.
    for i in range(100):
        compressor.add_experience(f"big theme alpha word {i}", "source_a")
    for i in range(20):
        compressor.add_experience(f"small theme beta word {i}", "source_b")
    compressor.compress()
    top = compressor.get_top_principles(5)
    assert len(top) >= 1
    efficiencies = [p.compression_efficiency for p in top]
    assert efficiencies == sorted(efficiencies, reverse=True)


def test_total_experiences_count():
    compressor = IdentityCompression(batch_size=100)
    for i in range(7):
        compressor.add_experience("some observed event detail", "stream")
    assert compressor.total_experiences == 7
    assert compressor.buffer_size == 7


def test_overall_compression_rate_zero_when_no_principles():
    compressor = IdentityCompression(batch_size=100)
    assert compressor.overall_compression_rate == 0.0


def test_to_dict_roundtrip_shape():
    compressor = IdentityCompression(batch_size=100)
    for i in range(60):
        compressor.add_experience("agent prefers quick concise feedback", "feedback")
    compressor.compress()

    d = compressor.to_dict()
    assert d["total_experiences_received"] == 60
    assert d["total_experiences_compressed"] == 60
    assert d["total_compression_cycles"] == 1
    assert d["buffer_size"] == 0
    assert isinstance(d["principles"], list)
    assert len(d["principles"]) >= 1
    assert isinstance(d["identity_markers"], dict)
    assert isinstance(d["recent_compressions"], list)
    assert d["recent_compressions"][0]["input"] == 60


def test_compression_report_dataclass_fields():
    r = CompressionReport(
        cycle=1,
        experiences_input=10,
        principles_extracted=1,
        markers_generated=["m"],
        compression_rate=10.0,
        identity_delta={"a": 1},
    )
    assert r.cycle == 1
    assert r.experiences_input == 10
    assert r.principles_extracted == 1
    assert r.compression_rate == 10.0


def test_experience_tag_dataclass_fields():
    tag = ExperienceTag(source="council", confidence=0.9, context_hash="abc")
    assert tag.source == "council"
    assert tag.confidence == 0.9
    assert tag.context_hash == "abc"
    assert tag.timestamp > 0

"""Contract tests for ProxyStream — tracks proxy objects when direct
detection is impossible (Λ3.4: adaptive capacity, not silent failure).

With proxy_mode in the world metadata it produces a proxy_track intent with
a real ProxyReport-derived payload; without it, it idles. detect_fn is an
injectable seam so the numpy-based path can be exercised deterministically.
"""
import numpy as np
import pytest

from telos.core.perception.proxy import (
    ProxyStream, ProxyReport, compute_motion_hotspots,
)
from telos.core.ledger.skill_library import SkillLibrary
from telos.world.world import World


def _world(**metadata):
    w = World(state=np.zeros(2))
    w.metadata = dict(metadata)
    return w


def test_idles_outside_proxy_mode():
    stream = ProxyStream(SkillLibrary())
    intent = stream.process(_world())
    assert intent.intent_type == "proxy_idle"
    assert intent.confidence == 0.1


def test_proxy_track_with_state_estimate():
    stream = ProxyStream(SkillLibrary())
    intent = stream.process(_world(proxy_mode=True, frame_width=640, frame_height=480))
    assert intent.intent_type == "proxy_track"
    assert intent.params["method"] == "state_estimate"
    assert intent.params["estimated_position"] == [320.0, 240.0]
    assert intent.metadata["proxy_confidence"] == pytest.approx(0.15)


def test_motion_based_proxy_reports_hotspots():
    stream = ProxyStream(SkillLibrary())
    # A real moving bright spot between two frames (numpy diff path).
    prev = np.zeros((32, 32), dtype=np.uint8)
    cur = prev.copy()
    cur[16, 16] = 255
    w = _world(proxy_mode=True, frame_data=cur)
    # First frame: no previous gray -> no motion yet, state fallback.
    intent1 = stream.process(w)
    assert intent1.params["method"] in ("state_estimate", "motion_hotspot")
    # Second frame with prev_gray set internally -> motion hotspots.
    intent2 = stream.process(w)
    assert intent2.params["motion_hotspots"]
    assert intent2.params["estimated_position"] is not None


def test_compute_motion_hotspots_finds_motion():
    prev = np.zeros((16, 16), dtype=np.uint8)
    cur = prev.copy()
    cur[5, 7] = 200
    hotspots = compute_motion_hotspots(prev, cur, top_n=5, percentile=85)
    # With cv2 installed the farneback flow path runs; without it the numpy
    # diff path. Both must return a non-empty list of hotspot dicts whenever
    # there IS motion (contract: motion is surfaced, never silently dropped).
    assert hotspots
    assert set(hotspots[0]) == {"x", "y", "magnitude"}


def test_compute_motion_hotspots_returns_list_of_dicts():
    prev = np.zeros((16, 16), dtype=np.uint8)
    cur = prev.copy()
    cur[3, 3] = 255
    for h in compute_motion_hotspots(prev, cur):
        assert set(h) == {"x", "y", "magnitude"}


def test_hotspots_are_bounded_by_top_n():
    prev = np.zeros((16, 16), dtype=np.uint8)
    cur = prev.copy()
    cur[5, 7] = 200
    hotspots = compute_motion_hotspots(prev, cur, top_n=3, percentile=85)
    assert len(hotspots) <= 3
    for h in hotspots:
        assert set(h) == {"x", "y", "magnitude"}


def test_reset_proxy_starts_fresh_cycle():
    stream = ProxyStream(SkillLibrary())
    cur = np.zeros((16, 16), dtype=np.uint8)
    # First frame establishes prev_gray; second frame produces motion context.
    stream.process(_world(proxy_mode=True, frame_data=cur))
    assert stream._prev_gray is not None
    # reset_proxy=True clears the motion memory (recomputes from the fresh
    # frame) and must not crash: still a valid proxy_track intent.
    intent = stream.process(_world(proxy_mode=True, frame_data=cur,
                                   reset_proxy=True))
    assert intent.intent_type == "proxy_track"
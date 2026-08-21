"""Tests for PerceptionQuality — resolution adequacy analysis and the
QualityReport contract."""

from telos.core.perception.quality import PerceptionQuality, QualityReport


def _assess(w, h, target=None):
    return PerceptionQuality().assess(w, h, target)


class TestQualityReport:
    def test_to_dict_rounds_and_converts(self):
        r = QualityReport(
            quality_score=0.5543,
            resolution=(640, 480),
            target_size_px=20.0,
            notes="n",
            proxy_recommended=True,
        )
        d = r.to_dict()
        assert d["quality_score"] == 0.554
        assert d["resolution"] == [640, 480]
        assert d["target_size_px"] == 20.0
        assert d["proxy_recommended"] is True
        assert d["notes"] == "n"


class TestAssess:
    def test_invalid_dimensions_zero_quality_proxy(self):
        for w, h in ((0, 100), (100, 0), (-5, 10), (0, 0)):
            r = _assess(w, h)
            assert r.quality_score == 0.0
            assert r.proxy_recommended is True
            assert "Invalid frame dimensions" in r.notes

    def test_hd_resolution_adequate_quality(self):
        r = _assess(1280, 720, 30)
        assert r.quality_score == 0.9
        assert r.proxy_recommended is False
        assert r.notes == "adequate quality"

    def test_low_resolution_small_target_proxy(self):
        r = _assess(200, 150, 5)
        assert r.proxy_recommended is True
        assert r.quality_score < 0.35
        assert "low resolution" in r.notes
        assert "target too small" in r.notes

    def test_wide_aspect_ratio_penalty(self):
        r = _assess(2000, 100)
        assert r.quality_score < 0.35
        assert "unusual aspect ratio" in r.notes
        # extreme aspect adds the max 0.1 penalty
        assert r.params["aspect_penalty"] == 0.1

    def test_target_none_scores_from_resolution_only(self):
        r = _assess(1280, 720, None)
        # size_score = resolution_score * 0.5
        assert r.params["size_score"] == 0.5
        assert r.quality_score == 0.4 * 1.0 + 0.5 * 0.5

    def test_params_fields_present(self):
        r = _assess(640, 480, 15)
        assert set(r.params) == {"resolution_score", "size_score", "aspect_penalty"}

    def test_quality_score_bounded(self):
        for w, h, t in ((1280, 720, 200), (10, 10, 2), (8000, 4000, 1000)):
            r = _assess(w, h, t)
            assert 0.0 <= r.quality_score <= 1.0

    def test_very_large_target_caps_size_score(self):
        r = _assess(1280, 720, 500)
        # size capped at 1.0; score = 0.4*1.0 + 0.5*1.0 = 0.9 (never exceeds)
        assert r.params["size_score"] == 1.0
        assert r.quality_score == 0.9
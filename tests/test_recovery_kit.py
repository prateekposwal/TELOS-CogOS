"""recovery_kit unit tests — pure math + gate logic (no key material)."""
import math
import pytest

from recovery_kit.space import (CHECKSUM_BITS, estimate, load_wordlist,
                                slot_candidates, verdict, fee_viability)


@pytest.fixture(scope="module")
def wl():
    return load_wordlist()


def test_wordlist_exact(wl):
    assert len(wl) == 2048 and len(set(wl)) == 2048


def test_bip39_unique_4letter_prefixes(wl):
    prefixes = [w[:4] for w in wl]
    assert len(set(prefixes)) == 2048  # documented BIP-39 design property


def test_full_space_12_words():
    res = estimate(["?"] * 12)
    assert res["raw_combinations"] == 2048 ** 12
    # expected valid fraction = 1/16 for 12 words
    assert abs(res["valid_mnemonics_est"] - 2048 ** 12 / 16) <= 1


def test_known_word_reduces_space():
    full = estimate(["?"] * 12)["valid_mnemonics_est"]
    one = estimate(["abandon"] + ["?"] * 11)["valid_mnemonics_est"]
    assert math.isclose(full / one, 2048, rel_tol=0.01)


def test_prefix_counting_exact(wl):
    assert slot_candidates("prefix:elep", wl) == 1      # elephant
    assert slot_candidates("prefix:exa", wl) >= 2       # examine, example
    assert slot_candidates("salt", wl) == 1
    with pytest.raises(ValueError):
        slot_candidates("notaword", wl)


def test_verdict_thresholds():
    tiny = {"valid_mnemonics_est": 10 ** 4}
    huge = {"valid_mnemonics_est": 10 ** 16}
    assert "VIABLE" in verdict(tiny)
    assert "REJECT" in verdict(huge)


def test_fee_viability_gate():
    res = {"compute_cost_usd_full": 100.0}
    fv = fee_viability(res, value_usd=20_000, fee_rate=0.10,
                       assumed_success_prob=0.5)
    assert fv["expected_fee_usd"] == 2000 and fv["ev_usd"] == 900 and fv["accept_on_ev"]
    bad = fee_viability(res, value_usd=500, fee_rate=0.10, assumed_success_prob=0.2)
    assert not bad["accept_on_ev"]  # $50 fee vs $100 cost


def test_checksum_table():
    assert CHECKSUM_BITS[12] == 4 and CHECKSUM_BITS[24] == 8

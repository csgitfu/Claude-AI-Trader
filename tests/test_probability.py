from trader.agents.probability import Estimate, _normalize


def test_probabilities_renormalize_to_one():
    e = Estimate(ticker="X", p_up=0.4, p_flat=0.4, p_down=0.4,
                 expected_return=0.05, implied_vol=0.3, conviction=3, summary="")
    _normalize(e)
    assert abs(e.p_up + e.p_flat + e.p_down - 1.0) < 1e-9


def test_vol_clamped_to_range():
    e = Estimate(ticker="X", p_up=0.3, p_flat=0.4, p_down=0.3,
                 expected_return=0.05, implied_vol=5.0, conviction=3, summary="")
    _normalize(e)
    assert e.implied_vol == 1.5

    e2 = Estimate(ticker="X", p_up=0.3, p_flat=0.4, p_down=0.3,
                  expected_return=0.05, implied_vol=0.01, conviction=3, summary="")
    _normalize(e2)
    assert e2.implied_vol == 0.1


def test_zero_probs_fallback_to_uniform():
    e = Estimate(ticker="X", p_up=0.0, p_flat=0.0, p_down=0.0,
                 expected_return=0.0, implied_vol=0.3, conviction=3, summary="")
    _normalize(e)
    assert abs(e.p_up - 1/3) < 1e-6
    assert abs(e.p_flat - 1/3) < 1e-6
    assert abs(e.p_down - 1/3) < 1e-6


def test_conviction_clamped():
    e = Estimate(ticker="X", p_up=0.3, p_flat=0.4, p_down=0.3,
                 expected_return=0.05, implied_vol=0.3, conviction=99, summary="")
    _normalize(e)
    assert e.conviction == 5

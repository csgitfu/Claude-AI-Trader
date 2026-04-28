import pytest
from pydantic import ValidationError

from trader.helpers.schemas import (
    DebateOutput,
    ProbEstimate,
    ScoreEntry,
    ScorerBatchOutput,
)


def test_score_entry_valid():
    e = ScoreEntry(ticker="AAPL", score=78, one_liner="solid quality", flags=[])
    assert e.score == 78


def test_score_entry_rejects_out_of_range():
    with pytest.raises(ValidationError):
        ScoreEntry(ticker="AAPL", score=150, one_liner="x")


def test_scorer_batch_round_trip():
    payload = {"scores": [{"ticker": "AAPL", "score": 78, "one_liner": "x", "flags": []}]}
    parsed = ScorerBatchOutput.model_validate(payload)
    assert parsed.scores[0].ticker == "AAPL"
    assert parsed.model_dump() == payload


def test_debate_output_required_fields():
    with pytest.raises(ValidationError):
        DebateOutput(ticker="AAPL", bull="...")  # missing bear


def test_prob_estimate_bounds():
    e = ProbEstimate(
        ticker="AAPL",
        p_outperform=0.62,
        expected_alpha_bps=180.0,
        conviction=0.55,
        sizing_hint=0.06,
    )
    assert e.sizing_hint == 0.06

    with pytest.raises(ValidationError):
        ProbEstimate(
            ticker="AAPL",
            p_outperform=0.62,
            expected_alpha_bps=180.0,
            conviction=0.55,
            sizing_hint=0.20,  # over 0.10 cap
        )

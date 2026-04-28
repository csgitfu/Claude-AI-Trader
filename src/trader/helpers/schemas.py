from __future__ import annotations

from pydantic import BaseModel, Field


class ScoreEntry(BaseModel):
    ticker: str
    score: int = Field(ge=0, le=100)
    one_liner: str
    flags: list[str] = Field(default_factory=list)


class ScorerBatchOutput(BaseModel):
    scores: list[ScoreEntry]


class DebateOutput(BaseModel):
    ticker: str
    bull: str
    bear: str


class ProbEstimate(BaseModel):
    ticker: str
    p_outperform: float = Field(ge=0, le=1)
    expected_alpha_bps: float
    conviction: float = Field(ge=0, le=1)
    sizing_hint: float = Field(ge=0, le=0.10)


SCHEMA_REGISTRY: dict[str, type[BaseModel]] = {
    "scorer": ScorerBatchOutput,
    "debater": DebateOutput,
    "prob-estimator": ProbEstimate,
}

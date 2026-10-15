"""Versioned contracts for public-corpus experiments; never read private chats."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ExperimentConfig(Strict):
    dataset: Literal["agent-learning-v1", "agent-learning-v2", "agent-qa-v1.1"] = "agent-learning-v1"
    split: Literal["dev", "calibration", "holdout", "acceptance", "all"] = "dev"
    strategy: Literal["bm25", "vector", "hybrid"] = "bm25"
    expand: bool = True
    body_only: bool = False
    intent_filter: bool = True
    mode: Literal["retrieval", "generate", "judge", "oracle", "oracle_generate"] = "retrieval"
    live: bool = False
    call_budget: int = Field(default=0, ge=0, le=1000)
    token_budget: int = Field(default=0, ge=0, le=20_000_000)
    repeat: int = Field(default=1, ge=1, le=5)
    request_key: str = Field(min_length=8, max_length=100)
    name: str = Field(default="检索实验", min_length=1, max_length=100)
    allow_pending: bool = False

    @model_validator(mode="after")
    def budget(self):
        if self.dataset=="agent-qa-v1.1" and self.strategy=="vector":raise ValueError("八主题候选仅比较 BM25F 与 E5 RRF。")
        if self.mode != "retrieval" and (not self.live or self.call_budget < 1 or self.token_budget < 1):
            raise ValueError("真实生成/裁判须显式启用并提供调用次数和 token 预算")
        if self.mode == "retrieval" and (self.live or self.call_budget or self.token_budget):
            raise ValueError("离线检索实验不使用模型预算")
        return self


class ExperimentRun(Strict):
    id: str
    state: Literal["queued", "running", "completed", "cancelled", "interrupted", "failed", "budget_exhausted"]
    config: dict
    snapshot: dict
    completed: int
    total: int
    calls_reserved: int
    tokens_reserved: int
    created: float
    updated: float
    error: str | None = None


class Diagnostic(Strict):
    claim_id: str
    text: str = Field(max_length=10000)
    judgment: Literal["supported", "contradicted", "insufficient", "unjudgeable"]
    rationale: str = Field(max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=8)
    origin: Literal["automatic", "rule", "human"] = "rule"
    spans: list[dict] = Field(default_factory=list, max_length=8)


class ClaimReview(Strict):
    question_id: str = Field(min_length=1, max_length=64)
    repetition: int = Field(default=0, ge=0, le=4)
    claim_id: str = Field(min_length=1, max_length=64)
    judgment: Literal["supported", "contradicted", "insufficient", "unjudgeable"]
    rationale: str = Field(min_length=1, max_length=2000)


class DatasetReview(Strict):
    question_id: str = Field(min_length=1, max_length=64)
    rationale: str = Field(min_length=1, max_length=2000)


class ImportRequest(Strict):
    dataset: Literal["agent-learning-v1", "agent-learning-v2", "agent-qa-v1.1"] = "agent-learning-v1"
    split: Literal["dev", "calibration", "holdout", "acceptance", "all"] = "dev"
    request_key: str = Field(min_length=8, max_length=100)
    name: str = Field(default="离线结果导入", min_length=1, max_length=100)
    results: list[dict] = Field(min_length=1, max_length=500)

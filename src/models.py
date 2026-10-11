from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from src.contracts import EvidenceItem


class RequestContext(BaseModel):
    request: dict[str, Any]
    requester: dict[str, Any] | None = None
    manager: dict[str, Any] | None = None


class BudgetCheck(BaseModel):
    department: str | None = None
    annual_cost_usd: float | None = None
    available_usd: float | None = None
    remaining_usd: float | None = None
    status: Literal["within_budget", "insufficient", "unknown"] = "unknown"


class SoftwareMatch(BaseModel):
    software_id: str
    product_name: str
    vendor_name: str
    category: str
    scope: str
    match_reasons: list[str] = Field(default_factory=list)


class ExistingSoftwareResult(BaseModel):
    matches: list[SoftwareMatch] = Field(default_factory=list)
    purchase_history: list[dict[str, Any]] = Field(default_factory=list)


class VendorEvidence(BaseModel):
    vendor_name: str
    internal: dict[str, Any] | None = None
    external: dict[str, Any] | None = None
    external_status: Literal["available", "unavailable", "not_found"]
    external_error: str | None = None


class EvidencePack(BaseModel):
    context: RequestContext
    budget: BudgetCheck
    software: ExistingSoftwareResult
    vendor: VendorEvidence


class PolicyResult(BaseModel):
    evidence: list[EvidenceItem] = Field(default_factory=list)
    required_approvals: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)


RecommendationLabel = Literal[
    "Needs clarification before review",
    "Hold pending evidence verification",
    "Review existing option before purchase",
    "Route for required specialist reviews",
    "Proceed to required human approval",
]


class AgentNarrative(BaseModel):
    recommendation: RecommendationLabel = Field(
        description="One allowed advisory recommendation label; never final approval"
    )
    reasoning_summary: str = Field(
        description="Concise reasoning grounded only in supplied evidence"
    )
    next_step: str = Field(
        description="One concrete human-owned next action"
    )


class ReviewerNarrative(BaseModel):
    verdict: Literal["accept_draft", "revise_draft"]
    recommendation: RecommendationLabel
    next_step: str
    concerns: list[str] = Field(default_factory=list)

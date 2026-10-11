from __future__ import annotations

import os

from src.contracts import EvidenceItem, ProcurementDecision, RunTelemetry
from src.llm_client import DEFAULT_MODEL, draft_recommendation, review_recommendation
from src.models import AgentNarrative, EvidencePack, PolicyResult, ReviewerNarrative
from src.policy_engine import run_policy_checks
from src.telemetry import RunTelemetryCounter
from src.tools import check_budget, find_existing_software, get_request_context, get_vendor_evidence


def _recommendation(policy: PolicyResult) -> tuple[str, str]:
    if policy.missing_information:
        fields = ", ".join(policy.missing_information)
        return (
            "Needs clarification before review",
            f"Ask the requester to provide {fields}; then rerun the policy and evidence checks.",
        )
    if "budget_insufficient" in policy.risk_flags:
        return (
            "Route for budget exception and specialist review",
            "Send the evidence package to Finance and every listed specialist before any purchasing decision.",
        )
    if "vendor_risk_unavailable" in policy.risk_flags:
        return (
            "Hold pending evidence verification",
            "Ask Security to verify the unavailable vendor evidence and complete all listed reviews before proceeding.",
        )
    if "conflicting_vendor_evidence" in policy.risk_flags:
        return (
            "Hold pending evidence verification",
            "Ask Security to reconcile the internal and external vendor records before proceeding.",
        )
    specialist_flags = {
        "security_review_required",
        "privacy_review_required",
        "legal_review_required",
        "vendor_review_expired",
    }
    if specialist_flags.intersection(policy.risk_flags):
        return (
            "Route for required specialist reviews",
            f"Send the evidence package to {', '.join(policy.required_approvals)} for human review.",
        )
    if "existing_tool_overlap" in policy.risk_flags:
        return (
            "Review existing option before purchase",
            "Confirm whether the catalogued option or existing capacity meets the stated need, then obtain the listed approvals.",
        )
    return (
        "Proceed to required human approval",
        f"Send the evidence package to {', '.join(policy.required_approvals)}; the copilot does not approve purchases.",
    )


def _safe_narrative(
    policy: PolicyResult,
    candidate: AgentNarrative | ReviewerNarrative | None,
) -> tuple[str, str]:
    """Merge model wording without letting it weaken deterministic controls."""
    fallback = _recommendation(policy)
    if candidate is None:
        return fallback

    unsafe_to_proceed = bool(
        policy.missing_information
        or {
            "budget_insufficient",
            "security_review_required",
            "privacy_review_required",
            "legal_review_required",
            "vendor_risk_unavailable",
            "conflicting_vendor_evidence",
        }.intersection(policy.risk_flags)
    )
    if unsafe_to_proceed and candidate.recommendation == "Proceed to required human approval":
        return fallback
    if policy.missing_information and candidate.recommendation != "Needs clarification before review":
        return fallback
    return candidate.recommendation, candidate.next_step.strip()[:500]


def _surface_model_fallback(policy: PolicyResult, error: str | None, attempted: bool, stage: str) -> None:
    if not error:
        return
    flag = "model_unavailable" if attempted else "model_not_configured"
    if flag not in policy.risk_flags:
        policy.risk_flags.append(flag)
    policy.evidence.append(
        EvidenceItem(
            source="gemini_reasoning",
            finding=f"{stage} AI step was unavailable ({error}); deterministic safe fallback was used.",
            reference=os.getenv("MODEL_NAME", DEFAULT_MODEL),
        )
    )


def _gather(request_id: str, telemetry: RunTelemetryCounter) -> EvidencePack:
    telemetry.record_tool_call("request_context_tool")
    context = get_request_context(request_id)
    telemetry.record_tool_call("budget_tool")
    budget = check_budget(context)
    telemetry.record_tool_call("software_catalog_tool")
    software = find_existing_software(context)
    telemetry.record_tool_call("vendor_risk_tool")
    vendor = get_vendor_evidence(str(context.request.get("vendor_name") or ""))
    return EvidencePack(context=context, budget=budget, software=software, vendor=vendor)


def run_single_agent(request_id: str) -> ProcurementDecision:
    """Architecture A: one evidence/recommendation stage with deterministic guardrails."""
    telemetry = RunTelemetryCounter()
    pack = _gather(request_id, telemetry)
    telemetry.record_tool_call("policy_engine")
    policy = run_policy_checks(pack)
    model_result = draft_recommendation(pack, policy)
    if model_result.attempted:
        telemetry.record_llm_call()
    if model_result.value is None:
        _surface_model_fallback(policy, model_result.error, model_result.attempted, "Analyst")
    draft = model_result.value if isinstance(model_result.value, AgentNarrative) else None
    recommendation, next_step = _safe_narrative(policy, draft)
    return ProcurementDecision(
        request_id=request_id,
        recommendation=recommendation,
        evidence=policy.evidence,
        required_approvals=policy.required_approvals,
        missing_information=policy.missing_information,
        risk_flags=policy.risk_flags,
        next_step=next_step,
        human_review_required=True,
        telemetry=RunTelemetry(
            llm_calls=telemetry.llm_calls,
            tool_calls=telemetry.tool_calls,
            tool_names=telemetry.tool_names,
        ),
    )


def run_staged_agents(request_id: str) -> ProcurementDecision:
    """Architecture B: analyst draft followed by one bounded policy/risk review."""
    telemetry = RunTelemetryCounter()
    pack = _gather(request_id, telemetry)
    telemetry.record_tool_call("policy_engine")
    policy = run_policy_checks(pack)

    draft_result = draft_recommendation(pack, policy)
    if draft_result.attempted:
        telemetry.record_llm_call()
    if draft_result.value is None:
        _surface_model_fallback(policy, draft_result.error, draft_result.attempted, "Analyst")
    model_draft = draft_result.value if isinstance(draft_result.value, AgentNarrative) else None

    reviewer_result = None
    if model_draft is not None:
        reviewer_result = review_recommendation(pack, policy, model_draft)
        if reviewer_result.attempted:
            telemetry.record_llm_call()
        if reviewer_result.value is None:
            _surface_model_fallback(policy, reviewer_result.error, reviewer_result.attempted, "Reviewer")
    reviewed = (
        reviewer_result.value
        if reviewer_result is not None and isinstance(reviewer_result.value, ReviewerNarrative)
        else model_draft
    )
    recommendation, next_step = _safe_narrative(policy, reviewed)

    return ProcurementDecision(
        request_id=request_id,
        recommendation=recommendation,
        evidence=policy.evidence,
        required_approvals=policy.required_approvals,
        missing_information=policy.missing_information,
        risk_flags=policy.risk_flags,
        next_step=next_step,
        human_review_required=True,
        telemetry=RunTelemetry(
            llm_calls=telemetry.llm_calls,
            tool_calls=telemetry.tool_calls,
            tool_names=telemetry.tool_names,
        ),
    )

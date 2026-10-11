from __future__ import annotations

import re
from datetime import date

from src.contracts import EvidenceItem
from src.models import EvidencePack, PolicyResult

REFERENCE_DATE = date(2026, 9, 30)
SENSITIVE_DATA = {
    "source_code",
    "production_data",
    "production_telemetry",
    "confidential_documents",
    "employee_pii",
    "customer_pii",
    "credentials",
    "secrets",
}
PRIVACY_DATA = {"employee_pii", "customer_pii"}
INJECTION_PATTERNS = (
    r"\bignore\b.{0,40}\b(rules?|policy|instructions?)\b",
    r"\b(bypass|override)\b.{0,30}\b(controls?|approval|policy)\b",
    r"\b(treat|mark)\b.{0,40}\b(approved|authorized)\b",
    r"\bapprove\b.{0,25}\b(immediately|automatically|without review)\b",
    r"\breveal\b.{0,20}\b(secret|api key|credentials?)\b",
)


def _add_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def _approval_band(amount: float) -> list[str]:
    if amount <= 1000:
        return ["Manager"]
    if amount <= 10000:
        return ["Department Head", "Procurement"]
    if amount <= 25000:
        return ["Department Head", "Finance", "Procurement"]
    return ["Department Head", "Finance", "CFO", "Procurement"]


def _is_prompt_injection(text: str) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL) for pattern in INJECTION_PATTERNS)


def _review_is_expired(review_date: object) -> bool:
    if not review_date:
        return False
    try:
        parsed = date.fromisoformat(str(review_date))
    except ValueError:
        return True
    return (REFERENCE_DATE - parsed).days > 365


def _security_state(value: object) -> str:
    """Map wording differences to policy-equivalent states before comparison."""
    normalized = str(value or "").strip().casefold().replace(" ", "_")
    if normalized == "approved":
        return "approved"
    if normalized == "expired":
        return "expired"
    if normalized in {"pending", "not_completed", "incomplete"}:
        return "incomplete"
    return "unknown"


def run_policy_checks(pack: EvidencePack) -> PolicyResult:
    """Tool 5: apply non-negotiable deterministic policy rules."""
    request = pack.context.request
    evidence: list[EvidenceItem] = []
    approvals: list[str] = []
    missing: list[str] = []
    flags: list[str] = []

    required = {
        "requester_id": "requester",
        "product_name": "product",
        "vendor_name": "vendor",
        "annual_cost_usd": "annual cost",
        "user_count": "user/license count",
        "business_justification": "business purpose",
        "data_access_level": "data access level",
        "requested_integrations": "required integrations",
    }
    for field, label in required.items():
        value = request.get(field)
        if value is None or (isinstance(value, str) and (not value.strip() or value.strip().casefold() == "unknown")):
            missing.append(label)
    if pack.context.requester is None:
        _add_unique(missing, "valid requester and department")
    if missing:
        _add_unique(flags, "missing_information")
        evidence.append(
            EvidenceItem(
                source="request_context_tool",
                finding=f"Material request information is missing: {', '.join(missing)}.",
                reference=str(request.get("request_id", "unknown")),
            )
        )
    else:
        requester = pack.context.requester or {}
        evidence.append(
            EvidenceItem(
                source="request_context_tool",
                finding=(
                    f"{requester.get('name')} from {requester.get('department')} requested "
                    f"{request.get('product_name')} for {request.get('user_count')} users."
                ),
                reference=str(request.get("request_id")),
            )
        )

    untrusted_text = " ".join(
        str(request.get(field) or "")
        for field in ("business_justification", "product_name", "vendor_name")
    )
    untrusted_text += " " + str((pack.vendor.internal or {}).get("notes") or "")
    untrusted_text += " " + str((pack.vendor.external or {}).get("notes") or "")
    if _is_prompt_injection(untrusted_text):
        _add_unique(flags, "prompt_injection_detected")
        evidence.append(
            EvidenceItem(
                source="policy_engine",
                finding="Untrusted request text attempted to change approval or policy behavior; it was ignored.",
                reference="Policy section 9",
            )
        )

    amount = pack.budget.annual_cost_usd
    if amount is not None:
        for approval in _approval_band(amount):
            _add_unique(approvals, approval)
        if pack.budget.status == "insufficient":
            _add_unique(flags, "budget_insufficient")
            _add_unique(approvals, "Finance")
            finding = (
                f"Annual cost ${amount:,.0f} exceeds {pack.budget.department}'s available "
                f"software budget of ${pack.budget.available_usd:,.0f} by ${-pack.budget.remaining_usd:,.0f}."
            )
        elif pack.budget.status == "within_budget":
            finding = (
                f"Annual cost ${amount:,.0f} is within {pack.budget.department}'s available "
                f"software budget of ${pack.budget.available_usd:,.0f}."
            )
        else:
            finding = "The department budget could not be verified."
        evidence.append(EvidenceItem(source="budget_tool", finding=finding, reference=pack.budget.department))

        evidence.append(
            EvidenceItem(
                source="policy_engine",
                finding=f"The ${amount:,.0f} annual amount requires: {', '.join(_approval_band(amount))}.",
                reference="Policy section 4",
            )
        )

    if pack.software.matches:
        _add_unique(flags, "existing_tool_overlap")
        match_text = "; ".join(
            f"{match.product_name} ({match.scope}; {', '.join(match.match_reasons)} match)"
            for match in pack.software.matches[:3]
        )
        evidence.append(
            EvidenceItem(
                source="software_catalog_tool",
                finding=f"Potential approved-software overlap found: {match_text}.",
                reference=",".join(match.software_id for match in pack.software.matches[:3]),
            )
        )
    else:
        evidence.append(
            EvidenceItem(
                source="software_catalog_tool",
                finding="No exact vendor, product, or same-category catalog match was found.",
                reference="software_catalog.csv",
            )
        )

    internal = pack.vendor.internal or {}
    external = pack.vendor.external or {}
    if internal:
        evidence.append(
            EvidenceItem(
                source="vendor_registry_tool",
                finding=(
                    f"Internal vendor status is {internal.get('procurement_status')}; security is "
                    f"{internal.get('security_status')}; legal terms are {internal.get('legal_terms_status')}."
                ),
                reference=str(internal.get("vendor_id")),
            )
        )

    if pack.vendor.external_status != "available":
        _add_unique(flags, "vendor_risk_unavailable")
        _add_unique(flags, "security_review_required")
        _add_unique(approvals, "Security")
        evidence.append(
            EvidenceItem(
                source="vendor_risk_api",
                finding=f"External vendor risk could not be verified: {pack.vendor.external_error}.",
                reference=f"/vendor-risk/{pack.vendor.vendor_name}",
            )
        )
    else:
        evidence.append(
            EvidenceItem(
                source="vendor_risk_api",
                finding=(
                    f"External risk is {external.get('risk_level')}; security assessment is "
                    f"{external.get('security_review_status')} dated {external.get('last_review_date')}."
                ),
                reference=f"/vendor-risk/{pack.vendor.vendor_name}",
            )
        )

    data_level = str(request.get("data_access_level") or "").strip().casefold()
    integrations = " ".join(str(value).casefold() for value in request.get("requested_integrations") or [])
    sensitive_use = data_level in SENSITIVE_DATA or "production cloud" in integrations
    external_security = _security_state(external.get("security_review_status"))
    external_expired = pack.vendor.external_status == "available" and (
        external_security == "expired" or _review_is_expired(external.get("last_review_date"))
    )
    internal_security = _security_state(internal.get("security_status"))
    internal_expired = bool(internal) and _review_is_expired(internal.get("security_review_date"))
    assessment_incomplete = (
        (bool(internal) and internal_security in {"incomplete", "unknown"})
        or (pack.vendor.external_status == "available" and external_security in {"incomplete", "unknown"})
    )

    if sensitive_use or external_expired or internal_expired or assessment_incomplete or not internal:
        _add_unique(flags, "security_review_required")
        _add_unique(approvals, "Security")
    if external_expired or internal_expired:
        _add_unique(flags, "vendor_review_expired")
    if sensitive_use:
        evidence.append(
            EvidenceItem(
                source="policy_engine",
                finding=f"The '{data_level}' use case or requested integration requires Security review.",
                reference="Policy section 5",
            )
        )

    if internal and external and internal_security != external_security:
        _add_unique(flags, "conflicting_vendor_evidence")
        _add_unique(flags, "security_review_required")
        _add_unique(approvals, "Security")
        evidence.append(
            EvidenceItem(
                source="policy_engine",
                finding=(
                    f"Vendor security evidence conflicts: internal='{internal.get('security_status')}', "
                    f"external='{external.get('security_review_status')}'."
                ),
                reference="Policy sections 5 and 10",
            )
        )

    outside_region = external.get("stores_data_outside_region") is True
    privacy_required = data_level in PRIVACY_DATA or (sensitive_use and outside_region)
    if privacy_required:
        _add_unique(flags, "privacy_review_required")
        _add_unique(approvals, "Privacy")
        evidence.append(
            EvidenceItem(
                source="policy_engine",
                finding="Personal or sensitive cross-region data processing requires Privacy review.",
                reference="Policy section 6",
            )
        )

    procurement_status = str(internal.get("procurement_status") or "").casefold()
    legal_status = str(internal.get("legal_terms_status") or "").casefold()
    new_vendor_threshold = procurement_status == "new" and amount is not None and amount >= 10000
    legal_required = new_vendor_threshold or legal_status not in {"approved", "standard"} or privacy_required
    if legal_required:
        _add_unique(flags, "legal_review_required")
        _add_unique(approvals, "Legal")
        evidence.append(
            EvidenceItem(
                source="policy_engine",
                finding="Vendor onboarding, legal-term, or material data-processing conditions require Legal review.",
                reference="Policy section 7",
            )
        )

    return PolicyResult(
        evidence=evidence,
        required_approvals=approvals,
        missing_information=missing,
        risk_flags=flags,
    )

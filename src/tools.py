from __future__ import annotations

from math import isnan
from typing import Any

import requests

from src import data_access, vendor_client
from src.models import (
    BudgetCheck,
    ExistingSoftwareResult,
    RequestContext,
    SoftwareMatch,
    VendorEvidence,
)


def _clean_record(record: dict[str, Any]) -> dict[str, Any]:
    """Convert pandas NaN values into JSON-safe nulls."""
    cleaned: dict[str, Any] = {}
    for key, value in record.items():
        if isinstance(value, float) and isnan(value):
            cleaned[key] = None
        else:
            cleaned[key] = value
    return cleaned


def _norm(value: object) -> str:
    return str(value or "").strip().casefold()


def get_request_context(request_id: str) -> RequestContext:
    """Tool 1: retrieve the request and its employee/reporting context."""
    request = data_access.get_request(request_id)
    employees = data_access.load_employees()
    requester_rows = employees[employees["employee_id"] == request.get("requester_id")]

    requester = None
    manager = None
    if not requester_rows.empty:
        requester = _clean_record(requester_rows.iloc[0].to_dict())
        manager_id = requester.get("manager_id")
        if manager_id:
            manager_rows = employees[employees["employee_id"] == manager_id]
            if not manager_rows.empty:
                manager = _clean_record(manager_rows.iloc[0].to_dict())

    return RequestContext(request=dict(request), requester=requester, manager=manager)


def check_budget(context: RequestContext) -> BudgetCheck:
    """Tool 2: compare annual request cost with the department snapshot."""
    department = context.requester.get("department") if context.requester else None
    amount = context.request.get("annual_cost_usd")
    if not department:
        return BudgetCheck(annual_cost_usd=amount)

    budgets = data_access.load_budgets()
    rows = budgets[budgets["department"].str.casefold() == _norm(department)]
    if rows.empty:
        return BudgetCheck(department=department, annual_cost_usd=amount)

    available = float(rows.iloc[0]["available_usd"])
    if amount is None:
        return BudgetCheck(department=department, available_usd=available)

    amount = float(amount)
    remaining = available - amount
    status = "within_budget" if remaining >= 0 else "insufficient"
    return BudgetCheck(
        department=department,
        annual_cost_usd=amount,
        available_usd=available,
        remaining_usd=remaining,
        status=status,
    )


def find_existing_software(context: RequestContext) -> ExistingSoftwareResult:
    """Tool 3: find transparent exact/vendor/category overlap and purchase history."""
    request = context.request
    product = _norm(request.get("product_name"))
    vendor = _norm(request.get("vendor_name"))
    category = _norm(request.get("category"))
    matches: list[SoftwareMatch] = []

    for raw in data_access.load_software_catalog().to_dict(orient="records"):
        row = _clean_record(raw)
        reasons: list[str] = []
        catalog_product = _norm(row.get("product_name"))
        if product and (product == catalog_product or product in catalog_product or catalog_product in product):
            reasons.append("product")
        if vendor and vendor == _norm(row.get("vendor_name")):
            reasons.append("vendor")
        if category and category == _norm(row.get("category")):
            reasons.append("category")
        if reasons:
            matches.append(
                SoftwareMatch(
                    software_id=str(row["software_id"]),
                    product_name=str(row["product_name"]),
                    vendor_name=str(row["vendor_name"]),
                    category=str(row["category"]),
                    scope=str(row["scope"]),
                    match_reasons=reasons,
                )
            )

    history = data_access.load_purchase_history()
    related = history[
        history["vendor_name"].str.casefold().eq(vendor)
        | history["product_name"].str.casefold().map(
            lambda value: bool(product and (product in value or value in product))
        )
    ]
    history_records = [_clean_record(row) for row in related.to_dict(orient="records")]
    return ExistingSoftwareResult(matches=matches, purchase_history=history_records)


def get_vendor_evidence(vendor_name: str) -> VendorEvidence:
    """Tool 4: compare the internal vendor registry with the external risk API."""
    vendors = data_access.load_vendors()
    rows = vendors[vendors["vendor_name"].str.casefold() == _norm(vendor_name)]
    internal = _clean_record(rows.iloc[0].to_dict()) if not rows.empty else None

    try:
        external = vendor_client.get_vendor_risk(vendor_name)
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        external_status = "not_found" if status == 404 else "unavailable"
        return VendorEvidence(
            vendor_name=vendor_name,
            internal=internal,
            external_status=external_status,
            external_error=f"Vendor-risk API returned HTTP {status or 'error'}",
        )
    except requests.RequestException as exc:
        return VendorEvidence(
            vendor_name=vendor_name,
            internal=internal,
            external_status="unavailable",
            external_error=f"Vendor-risk API unavailable: {type(exc).__name__}",
        )

    return VendorEvidence(
        vendor_name=vendor_name,
        internal=internal,
        external=external,
        external_status="available",
    )


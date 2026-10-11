from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from src.action_store import record_handoff
from src.contracts import ProcurementDecision
from src.solution import handle_request

ROOT = Path(__file__).resolve().parents[1]
RISK_DATA = json.loads((ROOT / "data" / "vendor_risk.json").read_text(encoding="utf-8"))


def fake_vendor_risk(vendor_name: str, timeout_seconds: float = 3.0) -> dict:
    record = RISK_DATA[vendor_name]
    if record.get("force_error"):
        response = requests.Response()
        response.status_code = 503
        raise requests.HTTPError("forced test outage", response=response)
    return {"vendor_name": vendor_name, **record}


class SolutionTests(unittest.TestCase):
    def run_request(self, request_id: str, architecture: str = "single") -> ProcurementDecision:
        with (
            patch("src.vendor_client.get_vendor_risk", side_effect=fake_vendor_risk),
            patch("src.llm_client._api_key", return_value=None),
        ):
            return handle_request(request_id, architecture=architecture)  # type: ignore[arg-type]

    def test_low_value_request_uses_manager_band(self):
        decision = self.run_request("REQ-1001")
        self.assertEqual(decision.required_approvals, ["Manager"])
        self.assertNotIn("budget_insufficient", decision.risk_flags)
        self.assertIn("model_not_configured", decision.risk_flags)

    def test_new_vendor_over_ten_thousand_requires_cross_functional_review(self):
        decision = self.run_request("REQ-1002")
        self.assertTrue({"Finance", "Procurement", "Security", "Legal"}.issubset(decision.required_approvals))
        self.assertIn("existing_tool_overlap", decision.risk_flags)
        self.assertNotIn("conflicting_vendor_evidence", decision.risk_flags)

    def test_sensitive_source_code_requires_security(self):
        decision = self.run_request("REQ-1003")
        self.assertIn("Security", decision.required_approvals)
        self.assertIn("security_review_required", decision.risk_flags)

    def test_budget_shortfall_is_calculated(self):
        decision = self.run_request("REQ-1005")
        self.assertIn("budget_insufficient", decision.risk_flags)
        self.assertIn("Finance", decision.required_approvals)
        self.assertTrue(any("$4,000" in item.finding for item in decision.evidence))

    def test_missing_values_and_injection_are_not_invented(self):
        decision = self.run_request("REQ-1006")
        self.assertEqual(
            decision.missing_information,
            ["annual cost", "user/license count", "data access level"],
        )
        self.assertIn("prompt_injection_detected", decision.risk_flags)
        self.assertIn("clarification", decision.recommendation.casefold())

    def test_conflicting_security_sources_are_surfaced(self):
        decision = self.run_request("REQ-1007")
        self.assertIn("conflicting_vendor_evidence", decision.risk_flags)
        self.assertIn("vendor_review_expired", decision.risk_flags)

    def test_vendor_api_outage_fails_safe(self):
        decision = self.run_request("REQ-1009")
        self.assertIn("vendor_risk_unavailable", decision.risk_flags)
        self.assertIn("Security", decision.required_approvals)
        self.assertTrue(decision.human_review_required)

    def test_staged_architecture_keeps_policy_controls(self):
        single = self.run_request("REQ-1005", "single")
        staged = self.run_request("REQ-1005", "staged")
        self.assertEqual(staged.required_approvals, single.required_approvals)
        self.assertEqual(staged.risk_flags, single.risk_flags)
        self.assertTrue(staged.human_review_required)

    def test_unknown_request_fails_clearly(self):
        with self.assertRaisesRegex(KeyError, "Unknown request_id"):
            self.run_request("REQ-DOES-NOT-EXIST")

    def test_human_handoff_is_append_only_and_human_owned(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "handoffs.jsonl"
            record_handoff("REQ-1002", "single", "Send for specialist review", "Security review needed.", path)
            record_handoff("REQ-1002", "single", "Keep decision pending", "Waiting for evidence.", path)
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["authority"] == "human" for row in rows))


if __name__ == "__main__":
    unittest.main()

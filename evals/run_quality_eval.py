from __future__ import annotations

import csv
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.contracts import ProcurementDecision
from src.solution import handle_request


def norm(value: object) -> str:
    return str(value).strip().casefold()


def group_present(items: list[object], group: list[str]) -> bool:
    texts = [norm(item) for item in items]
    return any(any(norm(token) in item for item in texts) for token in group)


def minimum_expectations_met(decision: ProcurementDecision, expectations: dict) -> bool:
    for field in (
        "required_approvals_any_groups",
        "risk_flags_any_groups",
        "missing_information_any_groups",
    ):
        items = {
            "required_approvals_any_groups": decision.required_approvals,
            "risk_flags_any_groups": decision.risk_flags,
            "missing_information_any_groups": decision.missing_information,
        }[field]
        if any(not group_present(items, group) for group in expectations.get(field, [])):
            return False
    if any(group_present(decision.risk_flags, [token]) for token in expectations.get("risk_flags_must_not_contain", [])):
        return False
    if len(decision.evidence) < expectations.get("min_evidence_items", 0):
        return False
    maximum = expectations.get("max_missing_information")
    if maximum is not None and len(decision.missing_information) > maximum:
        return False
    expected_human = expectations.get("human_review_required")
    return expected_human is None or decision.human_review_required == expected_human


def main() -> None:
    cases = json.loads((ROOT / "evals" / "public_cases.json").read_text(encoding="utf-8"))
    rows: list[dict[str, object]] = []

    for architecture in ("single", "staged"):
        for case in cases:
            started = time.perf_counter()
            decision = handle_request(case["request_id"], architecture=architecture)
            latency_ms = (time.perf_counter() - started) * 1000
            grounded = bool(decision.evidence) and all(
                item.source.strip() and item.finding.strip() and item.reference
                for item in decision.evidence
            )
            safe_language = all(
                token not in f"{decision.recommendation} {decision.next_step}".casefold()
                for token in ("auto-approve", "automatically approve", "purchase immediately")
            )
            policy_followed = minimum_expectations_met(decision, case["expectations"])
            human_correct = decision.human_review_required and safe_language
            correct_action = policy_followed and bool(decision.next_step.strip())
            telemetry = decision.telemetry
            rows.append(
                {
                    "case_id": case["case_id"],
                    "architecture": architecture,
                    "correct_next_action": correct_action,
                    "grounded_evidence": grounded,
                    "policy_followed": policy_followed,
                    "human_escalation_correct": human_correct,
                    "latency_ms": round(latency_ms, 1),
                    "llm_calls": telemetry.llm_calls if telemetry else "",
                    "tool_calls": telemetry.tool_calls if telemetry else "",
                    "notes": decision.recommendation,
                }
            )

    output = ROOT / "evals" / "evaluation_results.csv"
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    for architecture in ("single", "staged"):
        selected = [row for row in rows if row["architecture"] == architecture]
        quality_passes = sum(
            bool(row[metric])
            for row in selected
            for metric in (
                "correct_next_action",
                "grounded_evidence",
                "policy_followed",
                "human_escalation_correct",
            )
        )
        print(
            architecture,
            f"quality={quality_passes}/{len(selected) * 4}",
            f"mean_latency_ms={statistics.mean(float(row['latency_ms']) for row in selected):.1f}",
            f"mean_llm_calls={statistics.mean(int(row['llm_calls']) for row in selected):.1f}",
        )
    print(f"Results written to: {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

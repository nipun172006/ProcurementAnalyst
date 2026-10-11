from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG = ROOT / "runtime" / "human_handoffs.jsonl"
ALLOWED_ACTIONS = {
    "Request clarification",
    "Send for specialist review",
    "Keep decision pending",
}


def record_handoff(
    request_id: str,
    architecture: str,
    action: str,
    note: str,
    path: Path | None = None,
) -> dict:
    """Append a human-owned workflow action; never records purchase approval."""
    if action not in ALLOWED_ACTIONS:
        raise ValueError(f"Unsupported handoff action: {action}")
    clean_note = note.strip()
    if not clean_note:
        raise ValueError("A short handoff note is required")

    record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "architecture": architecture,
        "action": action,
        "note": clean_note,
        "authority": "human",
    }
    target = path or DEFAULT_LOG
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")
    return record

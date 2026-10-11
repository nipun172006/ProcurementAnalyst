from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from src.contracts import Architecture, ProcurementDecision
from src.agents import run_single_agent, run_staged_agents

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)


def handle_request(request_id: str, architecture: Architecture = "single") -> ProcurementDecision:
    """Assessment adapter.

    Keep this function callable by the public/hidden evaluation harness.
    Your internal implementation may use any framework, modules, agents, tools,
    deterministic checks, or orchestration strategy.
    """
    if architecture == "single":
        return run_single_agent(request_id)
    if architecture == "staged":
        return run_staged_agents(request_id)
    raise ValueError(f"Unsupported architecture: {architecture}")

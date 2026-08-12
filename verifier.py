#!/usr/bin/env python3
"""Deterministically verify governed agent execution traces."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

VERSION = "1.0.0"
VALID_STATUSES = {"succeeded", "failed", "cancelled"}


class InputError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def finding(ok: bool, summary: str, details: Optional[List[str]] = None) -> Dict[str, Any]:
    return {"passed": ok, "summary": summary, "details": details or []}


def require_mapping(value: Any, name: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise InputError(f"{name} must be an object")
    return value


def require_list(value: Any, name: str) -> List[Any]:
    if not isinstance(value, list):
        raise InputError(f"{name} must be an array")
    return value


def verify(trace: Dict[str, Any]) -> Dict[str, Any]:
    trace = require_mapping(trace, "trace")
    task = require_mapping(trace.get("task"), "task")
    policy = require_mapping(trace.get("policy"), "policy")
    events = require_list(trace.get("events"), "events")
    outcomes = set(require_list(trace.get("outcomes", []), "outcomes"))

    if not trace.get("trace_id"):
        raise InputError("trace_id is required")

    normalized_events: List[Dict[str, Any]] = []
    for index, raw_event in enumerate(events):
        event = require_mapping(raw_event, f"events[{index}]")
        normalized_events.append(event)

    dimensions: Dict[str, Dict[str, Any]] = {}

    required_outcomes = set(require_list(task.get("required_outcomes", []), "task.required_outcomes"))
    missing_outcomes = sorted(required_outcomes - outcomes)
    dimensions["task_success"] = finding(
        not missing_outcomes,
        "all required outcomes were observed" if not missing_outcomes else "required outcomes are missing",
        [f"missing outcome: {item}" for item in missing_outcomes],
    )

    semantic_errors: List[str] = []
    event_ids: List[str] = []
    for index, event in enumerate(normalized_events):
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            semantic_errors.append(f"events[{index}] has no event_id")
        else:
            event_ids.append(event_id)
        if not isinstance(event.get("resource"), str) or not event.get("resource"):
            semantic_errors.append(f"events[{index}] has no resource")
        if event.get("status") not in VALID_STATUSES:
            semantic_errors.append(f"events[{index}] has invalid status")
    duplicates = sorted({item for item in event_ids if event_ids.count(item) > 1})
    semantic_errors.extend(f"duplicate event_id: {item}" for item in duplicates)
    dimensions["semantic_consistency"] = finding(
        not semantic_errors,
        "event identities and state references are consistent" if not semantic_errors else "trace semantics are inconsistent",
        semantic_errors,
    )

    allowed_effects = set(require_list(policy.get("allowed_effects", []), "policy.allowed_effects"))
    review_required = set(require_list(policy.get("review_required", []), "policy.review_required"))
    effect_errors: List[str] = []
    for event in normalized_events:
        effect = event.get("effect")
        label = event.get("event_id", "<missing>")
        if effect not in allowed_effects:
            effect_errors.append(f"{label}: effect {effect!r} is not allowed")
        if effect in review_required:
            review = event.get("review")
            if not isinstance(review, dict) or review.get("status") != "approved" or not review.get("reviewer"):
                effect_errors.append(f"{label}: effect {effect!r} requires an approved named reviewer")
    dimensions["effect_safety"] = finding(
        not effect_errors,
        "all effects are permitted and reviewed where required" if not effect_errors else "effect policy violations found",
        effect_errors,
    )

    authority = require_mapping(policy.get("authority", {}), "policy.authority")
    authority_errors: List[str] = []
    for event in normalized_events:
        actor = event.get("actor")
        used = event.get("authority")
        allowed = authority.get(actor, [])
        if not isinstance(allowed, list) or used not in allowed:
            authority_errors.append(f"{event.get('event_id', '<missing>')}: {actor!r} lacks authority {used!r}")
    dimensions["authority_compliance"] = finding(
        not authority_errors,
        "every action used an explicit actor grant" if not authority_errors else "authority violations found",
        authority_errors,
    )

    evidence_required = set(require_list(policy.get("evidence_required", []), "policy.evidence_required"))
    evidence_errors: List[str] = []
    for event in normalized_events:
        if event.get("effect") in evidence_required and event.get("status") == "succeeded":
            evidence = event.get("evidence")
            if not isinstance(evidence, list) or not evidence or not all(isinstance(item, str) and item for item in evidence):
                evidence_errors.append(f"{event.get('event_id', '<missing>')}: successful effect lacks evidence")
    dimensions["evidence_sufficiency"] = finding(
        not evidence_errors,
        "required effect evidence is present" if not evidence_errors else "required evidence is missing",
        evidence_errors,
    )

    compensated = {event.get("compensates") for event in normalized_events if event.get("status") == "succeeded"}
    recovery_errors = [
        f"{event.get('event_id', '<missing>')}: failed mutating effect has no successful compensation"
        for event in normalized_events
        if event.get("status") == "failed"
        and event.get("effect") not in {"read", "observe"}
        and event.get("event_id") not in compensated
    ]
    dimensions["recovery_quality"] = finding(
        not recovery_errors,
        "failed mutating effects were compensated" if not recovery_errors else "uncompensated failed effects found",
        recovery_errors,
    )

    max_steps = task.get("max_steps")
    trajectory_ok = isinstance(max_steps, int) and max_steps >= 0 and len(normalized_events) <= max_steps
    trajectory_details = [] if trajectory_ok else [f"observed {len(normalized_events)} steps; max_steps is {max_steps!r}"]
    dimensions["trajectory_efficiency"] = finding(
        trajectory_ok,
        "trajectory stayed within the declared step envelope" if trajectory_ok else "trajectory exceeded or lacked a valid step envelope",
        trajectory_details,
    )

    budget = task.get("budget_usd")
    costs: List[float] = []
    cost_errors: List[str] = []
    for event in normalized_events:
        raw_cost = event.get("cost_usd", 0)
        if not isinstance(raw_cost, (int, float)) or isinstance(raw_cost, bool) or raw_cost < 0:
            cost_errors.append(f"{event.get('event_id', '<missing>')}: invalid cost_usd")
        else:
            costs.append(float(raw_cost))
    total_cost = round(sum(costs), 8)
    if not isinstance(budget, (int, float)) or isinstance(budget, bool) or budget < 0:
        cost_errors.append("task.budget_usd must be a non-negative number")
    elif total_cost > float(budget):
        cost_errors.append(f"observed cost ${total_cost:.8f} exceeds budget ${float(budget):.8f}")
    dimensions["cost"] = finding(
        not cost_errors,
        f"trajectory cost ${total_cost:.8f} is within budget" if not cost_errors else "cost policy violations found",
        cost_errors,
    )

    trace_digest = hashlib.sha256(canonical_bytes(trace)).hexdigest()
    passed = all(item["passed"] for item in dimensions.values())
    receipt_seed = f"bonfyre-agent-trace-verifier:{VERSION}:{trace_digest}:{str(passed).lower()}".encode("utf-8")
    return {
        "schema": "bonfyre.agent_trace_verification.v1",
        "verifier_version": VERSION,
        "trace_id": trace["trace_id"],
        "trace_digest_sha256": trace_digest,
        "passed": passed,
        "dimensions": dimensions,
        "metrics": {"event_count": len(normalized_events), "total_cost_usd": total_cost},
        "receipt_id": "bfv_" + hashlib.sha256(receipt_seed).hexdigest()[:24],
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, help="JSON trace to verify")
    parser.add_argument("--output", "-o", type=Path, help="write the verification receipt to this path")
    args = parser.parse_args(argv)
    try:
        trace = json.loads(args.trace.read_text(encoding="utf-8"))
        receipt = verify(trace)
    except (OSError, json.JSONDecodeError, InputError) as exc:
        print(json.dumps({"error": str(exc), "passed": False}), file=sys.stderr)
        return 2

    rendered = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

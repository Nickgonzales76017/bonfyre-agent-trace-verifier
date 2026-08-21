#!/usr/bin/env python3
"""Deterministically verify governed agent execution traces."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

VERSION = "1.2.1"
VALID_STATUSES = {"succeeded", "failed", "cancelled"}
CONTEXT_EVENT_TYPES = {"context_compaction", "context_strategy"}
MODEL_TURN_EVENT_TYPE = "model_turn"
PROVIDER_EVIDENCE_ORIGINS = {"subject", "host", "external"}

# Canonicalisation version. The trace digest is only comparable between two
# runs that canonicalised the same way, so this is recorded alongside the
# digest rather than left implicit.
CANONICALIZATION_VERSION = "2"


class InputError(ValueError):
    pass


def canonical_text(text: str) -> str:
    """Normalise text so that encoding differences are not identity differences.

    Sorting keys is not enough. The same trace captured on Windows and on
    Linux differs by line ending; the same string typed on macOS and pasted
    from a Linux terminal can differ by Unicode normal form. Neither is a
    behavioural difference, and if either changes the digest then the digest
    is not an identity -- it is a checksum over an accident of transport.

    Two normalisations, both narrow:

      NFC          combining sequences fold to their composed form, so
                   "café" and "café" are the same string
      LF endings   CRLF and lone CR both become LF

    This deliberately repairs normal form rather than rejecting it. A
    verifier that refuses a Windows-authored trace is not useful; one that
    silently gives it a different identity is worse.
    """
    text = unicodedata.normalize("NFC", text)
    return text.replace("\r\n", "\n").replace("\r", "\n")


def canonical_value(value: Any) -> Any:
    """Recursively canonicalise a decoded JSON value.

    Applies to dict KEYS as well as values -- a key differing only in normal
    form would otherwise survive sort_keys and change the preimage.
    """
    if isinstance(value, str):
        return canonical_text(value)
    if isinstance(value, dict):
        return {canonical_text(str(k)): canonical_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [canonical_value(v) for v in value]
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        # 1 and 1.0 are the same number; JSON round-trips make this common
        return int(value)
    return value


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        canonical_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


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


def _nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _context_management_dimension(
    task: Dict[str, Any],
    events: List[Dict[str, Any]],
) -> tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    required = task.get("require_context_events", False)
    if not isinstance(required, bool):
        raise InputError("task.require_context_events must be a boolean")

    context_events = [
        event for event in events if event.get("event_type") in CONTEXT_EVENT_TYPES
    ]
    if not required and not context_events:
        return None, {}

    errors: List[str] = []
    for event in context_events:
        label = event.get("event_id", "<missing>")
        context = event.get("context")
        if not isinstance(context, dict):
            errors.append(f"{label}: context-management event lacks a context object")
            continue

        before = context.get("before_tokens")
        after = context.get("after_tokens")
        strategy = context.get("strategy")
        if not _nonnegative_int(before):
            errors.append(f"{label}: context.before_tokens must be a non-negative integer")
        if not _nonnegative_int(after):
            errors.append(f"{label}: context.after_tokens must be a non-negative integer")
        if not isinstance(strategy, str) or not strategy:
            errors.append(f"{label}: context.strategy must be a non-empty string")
        if (
            event.get("event_type") == "context_compaction"
            and _nonnegative_int(before)
            and _nonnegative_int(after)
            and after > before
        ):
            errors.append(f"{label}: context compaction increased token count")

    if required and not context_events:
        errors.append("task requires first-class context-management events")

    return (
        finding(
            not errors,
            (
                "context-management events are explicit and measurable"
                if not errors
                else "context-management trace requirements were not met"
            ),
            errors,
        ),
        {
            "context_event_count": len(context_events),
            "context_event_types": sorted(
                {event["event_type"] for event in context_events}
            ),
        },
    )


def _provider_fidelity_dimension(
    task: Dict[str, Any],
    events: List[Dict[str, Any]],
) -> tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    required = task.get("require_provider_fidelity", False)
    if not isinstance(required, bool):
        raise InputError("task.require_provider_fidelity must be a boolean")

    subject_provider = task.get("subject_provider")
    if subject_provider is not None and (
        not isinstance(subject_provider, str) or not subject_provider
    ):
        raise InputError("task.subject_provider must be a non-empty string")
    canonical_subject_provider = (
        canonical_text(subject_provider)
        if isinstance(subject_provider, str)
        else None
    )

    model_turns = [
        event for event in events if event.get("event_type") == MODEL_TURN_EVENT_TYPE
    ]
    if not required and subject_provider is None and not model_turns:
        return None, {}

    errors: List[str] = []
    subject_turns = 0
    non_subject_turns = 0

    if required and subject_provider is None:
        errors.append("provider fidelity requires task.subject_provider")

    for event in model_turns:
        label = event.get("event_id", "<missing>")
        provider = event.get("provider")
        origin = event.get("evidence_origin")

        if not isinstance(provider, str) or not provider:
            errors.append(f"{label}: model turn has no provider")
        if origin not in PROVIDER_EVIDENCE_ORIGINS:
            errors.append(f"{label}: model turn has invalid or missing evidence_origin")
            continue

        if origin == "subject":
            subject_turns += 1
            if (
                canonical_subject_provider is not None
                and isinstance(provider, str)
                and canonical_text(provider) != canonical_subject_provider
            ):
                errors.append(
                    f"{label}: subject turn used a provider other than task.subject_provider"
                )
        else:
            # Host/external evidence is allowed, but it is counted separately
            # and can never silently satisfy the subject-provider requirement.
            non_subject_turns += 1

    if required and subject_turns == 0:
        errors.append("provider fidelity requires at least one subject-origin model turn")

    return (
        finding(
            not errors,
            (
                "subject turns preserve provider fidelity and foreign evidence is explicit"
                if not errors
                else "provider-fidelity requirements were not met"
            ),
            errors,
        ),
        {
            # The receipt must obey the same equivalence relation as its trace
            # digest. Emitting the raw spelling here would make NFC/NFD-equivalent
            # traces share an identity but serialize to different receipts.
            "subject_provider": canonical_subject_provider,
            "subject_model_turn_count": subject_turns,
            "non_subject_model_turn_count": non_subject_turns,
        },
    )


def _adapter_capability_dimension(
    trace: Dict[str, Any],
    task: Dict[str, Any],
) -> tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    if "required_capabilities" in task:
        required = require_list(
            task["required_capabilities"], "task.required_capabilities"
        )
    else:
        required = []
    if not all(isinstance(item, str) and item for item in required):
        raise InputError("task.required_capabilities must contain non-empty strings")

    capabilities_present = "adapter_capabilities" in trace
    capabilities_raw = trace.get("adapter_capabilities")
    if not required and not capabilities_present:
        return None, {}

    capabilities = require_mapping(capabilities_raw, "adapter_capabilities")
    available = require_list(capabilities.get("available", []), "adapter_capabilities.available")
    unavailable = require_list(
        capabilities.get("unavailable", []), "adapter_capabilities.unavailable"
    )
    if not all(isinstance(item, str) and item for item in available + unavailable):
        raise InputError("adapter capability entries must be non-empty strings")

    available_set = set(available)
    unavailable_set = set(unavailable)
    errors: List[str] = []
    overlap = sorted(available_set & unavailable_set)
    if overlap:
        errors.extend(f"capability declared both available and unavailable: {item}" for item in overlap)

    missing = sorted(set(required) - available_set)
    errors.extend(f"required capability unavailable: {item}" for item in missing)

    return (
        finding(
            not errors,
            (
                "adapter capability differences are explicit"
                if not errors
                else "adapter capability requirements were not met"
            ),
            errors,
        ),
        {
            "adapter_available_capabilities": sorted(available_set),
            "adapter_unavailable_capabilities": sorted(unavailable_set),
        },
    )


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
    specialty_metrics: Dict[str, Any] = {}

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

    context_dimension, context_metrics = _context_management_dimension(
        task, normalized_events
    )
    if context_dimension is not None:
        dimensions["context_management"] = context_dimension
        specialty_metrics.update(context_metrics)

    provider_dimension, provider_metrics = _provider_fidelity_dimension(
        task, normalized_events
    )
    if provider_dimension is not None:
        dimensions["provider_fidelity"] = provider_dimension
        specialty_metrics.update(provider_metrics)

    capability_dimension, capability_metrics = _adapter_capability_dimension(trace, task)
    if capability_dimension is not None:
        dimensions["adapter_capabilities"] = capability_dimension
        specialty_metrics.update(capability_metrics)

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
    metrics: Dict[str, Any] = {
        "event_count": len(normalized_events),
        "total_cost_usd": total_cost,
    }
    metrics.update(specialty_metrics)
    return {
        "schema": "bonfyre.agent_trace_verification.v1",
        "verifier_version": VERSION,
        "trace_id": trace["trace_id"],
        "trace_digest_sha256": trace_digest,
        # digests are only comparable across runs that canonicalised the
        # same way; recording this lets a consumer notice rather than
        # silently compare across a canonicalisation change
        "canonicalization_version": CANONICALIZATION_VERSION,
        "passed": passed,
        "dimensions": dimensions,
        "metrics": metrics,
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

#!/usr/bin/env python3
"""Deterministic, synthetic Helpdesk SLA environment projection."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


INITIAL_STATE: Dict[str, Any] = {
    "ticket": {
        "id": "HD-SYN-1042",
        "status": "open",
        "priority": "high",
        "assigned_team": "tier1",
        "customer_notified": False,
        "version": 1,
    }
}


class InvalidAction(ValueError):
    """Raised when an action violates the environment transition contract."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


class HelpdeskSLAEnvironment:
    """Small branch/reset/replay environment with explicit effects and authority."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> Dict[str, Any]:
        self.state = copy.deepcopy(INITIAL_STATE)
        self.events: List[Dict[str, Any]] = []
        return self.observe()

    def branch(self) -> "HelpdeskSLAEnvironment":
        candidate = HelpdeskSLAEnvironment()
        candidate.state = copy.deepcopy(self.state)
        candidate.events = copy.deepcopy(self.events)
        return candidate

    def observe(self) -> Dict[str, Any]:
        return {
            "state": copy.deepcopy(self.state),
            "state_id": hashlib.sha256(canonical_bytes(self.state)).hexdigest(),
            "step": len(self.events),
        }

    def step(
        self,
        action: str,
        *,
        reviewer: Optional[str] = None,
        evidence: Optional[str] = None,
    ) -> Dict[str, Any]:
        ticket = self.state["ticket"]
        if ticket["status"] == "closed":
            raise InvalidAction("ticket is already closed")

        event: Dict[str, Any] = {
            "event_id": f"evt-{len(self.events) + 1}",
            "actor": "support-agent",
            "action": action,
            "resource": f"ticket:{ticket['id']}",
            "status": "succeeded",
            "cost_usd": 0,
        }

        if action == "read_ticket":
            event.update(effect="read", authority="ticket:read")
        elif action == "assign_tier2":
            if not evidence:
                raise InvalidAction("assignment requires a version receipt")
            ticket["assigned_team"] = "tier2"
            ticket["version"] += 1
            event.update(effect="write", authority="ticket:assign", evidence=[evidence])
        elif action == "send_resolution":
            if ticket["assigned_team"] != "tier2":
                raise InvalidAction("resolution requires tier2 assignment")
            if not reviewer or not evidence:
                raise InvalidAction("external send requires named approval and evidence")
            ticket["customer_notified"] = True
            event.update(
                effect="external_send",
                authority="message:send",
                review={"status": "approved", "reviewer": reviewer},
                evidence=[evidence],
            )
        elif action == "close_ticket":
            if not ticket["customer_notified"]:
                raise InvalidAction("ticket cannot close before customer notification")
            if not evidence:
                raise InvalidAction("close requires a version receipt")
            ticket["status"] = "closed"
            ticket["version"] += 1
            event.update(effect="write", authority="ticket:close", evidence=[evidence])
        else:
            raise InvalidAction(f"unsupported action: {action}")

        self.events.append(event)
        return self.observe()

    def trace(self) -> Dict[str, Any]:
        outcomes: List[str] = []
        ticket = self.state["ticket"]
        if ticket["customer_notified"]:
            outcomes.append("customer.notified")
        if ticket["status"] == "closed":
            outcomes.append("ticket.closed")
        return {
            "trace_id": "helpdesk-sla-synthetic-v1",
            "task": {
                "required_outcomes": ["customer.notified", "ticket.closed"],
                "max_steps": 4,
                "budget_usd": 0,
            },
            "policy": {
                "allowed_effects": ["read", "write", "external_send"],
                "review_required": ["external_send"],
                "evidence_required": ["write", "external_send"],
                "authority": {
                    "support-agent": [
                        "ticket:read",
                        "ticket:assign",
                        "message:send",
                        "ticket:close",
                    ]
                },
            },
            "events": copy.deepcopy(self.events),
            "outcomes": outcomes,
        }

    @classmethod
    def replay(cls, actions: List[Dict[str, Any]]) -> "HelpdeskSLAEnvironment":
        environment = cls()
        for item in actions:
            environment.step(**item)
        return environment


def main() -> int:
    actions = json.loads(Path(__file__).with_name("passing_actions.json").read_text())
    environment = HelpdeskSLAEnvironment.replay(actions)
    print(json.dumps({"observation": environment.observe(), "trace": environment.trace()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

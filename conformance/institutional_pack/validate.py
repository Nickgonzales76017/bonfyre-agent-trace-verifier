#!/usr/bin/env python3
"""Offline validators for the public institutional conformance pack."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SPDX_CONTEXT = "https://spdx.org/rdf/3.0.1/spdx-context.jsonld"
SLSA_PREDICATE = "https://slsa.dev/provenance/v1"
OSPS_LEVEL_1 = {
    "OSPS-AC-01.01", "OSPS-AC-02.01", "OSPS-AC-03.01", "OSPS-AC-03.02",
    "OSPS-BR-01.01", "OSPS-BR-01.03", "OSPS-BR-03.01", "OSPS-BR-03.02",
    "OSPS-BR-07.01", "OSPS-DO-01.01", "OSPS-DO-02.01", "OSPS-GV-02.01",
    "OSPS-GV-03.01", "OSPS-LE-02.01", "OSPS-LE-02.02", "OSPS-LE-03.01",
    "OSPS-LE-03.02", "OSPS-QA-01.01", "OSPS-QA-01.02", "OSPS-QA-02.01",
    "OSPS-QA-04.01", "OSPS-QA-05.01", "OSPS-QA-05.02", "OSPS-VM-02.01",
}
ALLOWED_OSPS_STATUS = {"pass", "fail", "unverified", "not_applicable"}
CONTENT_ATTRIBUTES = {
    "gen_ai.input.messages", "gen_ai.output.messages", "gen_ai.system_instructions",
    "gen_ai.tool.call.arguments", "gen_ai.tool.call.result", "gen_ai.tool.definitions",
}


def load(name: str) -> Any:
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def _assert_ascii_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            assert key.isascii() and all(0x21 <= ord(c) <= 0x7F for c in key), key
            _assert_ascii_keys(child)
    elif isinstance(value, list):
        for child in value:
            _assert_ascii_keys(child)


def canonical_spdx_bytes(document: dict[str, Any]) -> bytes:
    _assert_ascii_keys(document)
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def validate_otel() -> dict[str, int]:
    trace = load("otel-action-trace.json")
    by_operation = {span["attributes"]["gen_ai.operation.name"]: span for span in trace["spans"]}
    assert {"invoke_agent", "execute_tool", "chat"} <= by_operation.keys()
    assert by_operation["invoke_agent"]["name"] == "invoke_agent verifier"
    assert by_operation["execute_tool"]["name"] == "execute_tool BonfyreProof"
    assert by_operation["chat"]["name"] == "chat gpt-5"
    assert by_operation["chat"]["attributes"]["gen_ai.provider.name"] == "openai"
    assert isinstance(by_operation["chat"]["attributes"]["gen_ai.usage.input_tokens"], int)
    if not trace["content_capture_opt_in"]:
        present = CONTENT_ATTRIBUTES.intersection(
            key for span in trace["spans"] for key in span["attributes"]
        )
        assert not present, f"content-bearing attributes require opt-in: {sorted(present)}"
    return {"spans": len(trace["spans"]), "content_attributes": 0}


def validate_osps() -> dict[str, int]:
    report = load("osps-v2026.02.19.json")
    assert report["baseline_version"] == "2026.02.19"
    controls = report["controls"]
    assert {item["id"] for item in controls} == OSPS_LEVEL_1
    assert len(controls) == len({item["id"] for item in controls})
    counts = {status: 0 for status in ALLOWED_OSPS_STATUS}
    for control in controls:
        assert control["status"] in ALLOWED_OSPS_STATUS
        assert control["evidence"] and all(isinstance(x, str) and x for x in control["evidence"])
        counts[control["status"]] += 1
    assert counts["fail"] >= 1, "a posture report must not hide the observed branch-protection gap"
    return counts


def validate_spdx() -> dict[str, str]:
    document = load("spdx-benchmark-bundle.jsonld")
    assert document["@context"] == SPDX_CONTEXT
    graph = document["@graph"]
    assert sum(node.get("type") == "SpdxDocument" for node in graph) == 1
    ids = [node["spdxId"] for node in graph]
    assert len(ids) == len(set(ids))
    canonical = canonical_spdx_bytes(document)
    # Spaces are valid inside string values; separators=(',', ':') removes
    # whitespace between JSON tokens, which is the SPDX canonical requirement.
    assert b"\n" not in canonical
    return {"sha256": hashlib.sha256(canonical).hexdigest()}


def validate_slsa() -> dict[str, Any]:
    provenance = load("slsa-provenance.json")
    assurance = load("slsa-assurance.json")
    artifact = HERE / "benchmark-task.txt"
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert provenance["_type"] == "https://in-toto.io/Statement/v1"
    assert provenance["predicateType"] == SLSA_PREDICATE
    assert provenance["subject"] == [{
        "name": "conformance/institutional_pack/benchmark-task.txt",
        "digest": {"sha256": digest},
    }]
    definition = provenance["predicate"]["buildDefinition"]
    assert definition["buildType"].endswith("/benchmark-pack/v1")
    assert definition["externalParameters"] == {"task": "secret-safe-audit-write"}
    assert assurance == {
        "claimedBuildLevel": 1,
        "signed": False,
        "note": "Subject and build expectations are verifiable; authenticity is not asserted until a trusted build platform signs the envelope.",
    }
    return {"artifact_sha256": digest, "claimed_build_level": 1, "signed": False}


def validate_sigstore() -> dict[str, str]:
    policy = load("sigstore-policy.json")
    command = policy["verification_command"]
    assert policy["bundle_required"] is True
    assert command[:2] == ["cosign", "verify-blob"]
    for flag in ("--bundle", "--certificate-identity-regexp", "--certificate-oidc-issuer"):
        assert flag in command
    forbidden = {"--check-claims=false", "--insecure-ignore-tlog", "--insecure-ignore-sct"}
    assert forbidden.isdisjoint(command)
    assert policy["status"] == "ready_for_signing"
    return {"command": shlex.join(command), "status": policy["status"]}


def validate_habitat() -> dict[str, int]:
    habitat = load("aurekai-commons.json")
    assert habitat["federation_boundary"] == "public"
    rooms = habitat["rooms"]
    assert len(rooms) == 3 and len({room["id"] for room in rooms}) == 3
    for room in rooms:
        assert room["source"] and room["status"] and room["ports"]
        assert room["asset_passport"]["contains_credentials"] is False
        assert all(port["kind"] and port["href"] for port in room["ports"])
    return {"rooms": len(rooms), "ports": sum(len(room["ports"]) for room in rooms)}


def validate_all() -> dict[str, Any]:
    lock = load("standards-lock.json")
    assert set(lock["standards"]) == {
        "opentelemetry_genai", "openssf_osps", "spdx", "sigstore_cosign", "slsa"
    }
    return {
        "opentelemetry": validate_otel(),
        "openssf_osps": validate_osps(),
        "spdx": validate_spdx(),
        "slsa": validate_slsa(),
        "sigstore": validate_sigstore(),
        "habitat": validate_habitat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="validate the complete pack")
    args = parser.parse_args()
    if not args.all:
        parser.error("use --all")
    print(json.dumps(validate_all(), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

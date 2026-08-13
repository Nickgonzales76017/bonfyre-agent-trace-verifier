# Institutional conformance pack

This pack turns one real external episode—credential-safe trace persistence in
[Bernstein PR #3734](https://github.com/sipyourdrink-ltd/bernstein/pull/3734)—into
five runnable interoperability artifacts and three public Habitat projections.
It is deliberately honest about scope: these checks are implementation
preflights, not certifications by the standards bodies.

Run everything offline with:

```bash
python3 conformance/institutional_pack/validate.py --all
```

The artifacts are pinned in `standards-lock.json`:

- `otel-action-trace.json` maps Bonfyre agent, model, and tool execution into
  the current OpenTelemetry GenAI model. Content-bearing attributes are denied
  unless an explicit capture opt-in is present.
- `osps-v2026.02.19.json` is a control-by-control Level 1 posture report for
  this repository. It records the unprotected primary branch as a failure and
  keeps remote-only controls unverified rather than guessing.
- `spdx-benchmark-bundle.jsonld` and the validator exercise SPDX 3.0.1 context,
  single-document, identifier, and canonical-JSON requirements. Full SPDX
  conformance additionally requires the official JSON Schema and OWL/SHACL
  validation linked in the lock.
- `slsa-provenance.json` binds a benchmark artifact digest to SLSA Provenance
  v1 fields and strict build expectations. It is explicitly unsigned Build L1
  material, not a Build L2/L3 claim.
- `sigstore-policy.json` renders an identity-bound `cosign verify-blob` command
  that requires a bundle, issuer, and certificate identity. No signature has
  been invented; issuance remains a release-workflow continuation.
- `aurekai-commons.json` exposes the live upstream episode, this conformance
  pack, and its benchmark task as three source-backed public Habitat rooms.

Primary sources:

- [OpenTelemetry GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai)
- [OpenSSF OSPS Baseline v2026.02.19](https://baseline.openssf.org/versions/2026-02-19)
- [SPDX 3.0.1 serialization rules](https://spdx.github.io/spdx-spec/v3.0.1/serializations/)
- [Sigstore blob verification](https://docs.sigstore.dev/cosign/verifying/verify/)
- [SLSA v1.2 artifact verification](https://slsa.dev/spec/v1.2/verifying-artifacts)

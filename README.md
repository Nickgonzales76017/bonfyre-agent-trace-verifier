# Bonfyre Agent Trace Verifier

A small, deterministic verifier for governed agent execution traces. It keeps eight evaluation dimensions separate instead of hiding safety failures inside one reward score:

- task success
- semantic consistency
- effect safety
- authority compliance
- evidence sufficiency
- recovery quality
- trajectory efficiency
- cost

The verifier uses only the Python standard library, performs no network calls, and emits a content-addressed JSON receipt. The same trace always produces the same digest and receipt ID.

## Identity continuity

The digest is an **identity**, not a checksum over an accident of transport. Two runs of the same agent recorded on different machines describe the same execution, and they must produce the same digest.

That requires canonicalising before hashing, and canonicalising more than key order:

| Encoding difference | Same digest? |
|---|---|
| Object key order | yes |
| `1` vs `1.0` | yes |
| CRLF vs LF line endings | yes, since v1.1.0 |
| Unicode NFD vs NFC | yes, since v1.1.0 |
| Normal form differing in a **key** | yes, since v1.1.0 |
| Genuinely different content | **no** — normalisation must not collapse real differences |

Before v1.1.0 the last four were wrong: sorting keys was not enough, so a trace captured on Windows and the same trace on Linux hashed differently. Normalisation now folds to NFC and LF, recursively, across keys and nested structures.

This is deliberately a **repair**, not a rejection. A verifier that refuses a Windows-authored trace is not useful; one that silently gives it a different identity is worse.

Receipts carry `canonicalization_version`, so a consumer can tell that two digests are not comparable rather than silently comparing across a canonicalisation change.

The same class of bug, found by a maintainer during upstream review of a SARIF finding addresser, is written up in the [Identity Continuity case study](https://github.com/sipyourdrink-ltd/bernstein/pull/3695) — where CRLF and NFD were each producing different identities for identical findings.

## Try it

```bash
python3 verifier.py examples/pass.json
python3 verifier.py examples/fail.json  # exits 1 and explains each failed dimension
python3 -m unittest discover -s tests -v
```

Passing traces exit `0`, policy failures exit `1`, and malformed inputs exit `2`.

## Use in GitHub Actions

Pin the action to a release and pass the repository-relative path to a trace:

```yaml
- name: Verify governed agent trace
  id: agent-trace
  uses: Nickgonzales76017/bonfyre-agent-trace-verifier@v1.2.0
  with:
    trace-path: artifacts/agent-trace.json

- name: Preserve verification receipt
  uses: actions/upload-artifact@v4
  with:
    name: agent-trace-receipt
    path: ${{ steps.agent-trace.outputs.receipt-path }}
```

The step fails for policy violations or malformed input. It exposes `passed`, `receipt-id`, `trace-digest`, and `receipt-path` outputs for later CI steps. The action invokes the same standard-library verifier and makes no network calls.

## Trace contract

Each trace declares the task envelope, policy, ordered events, and observed outcomes. Effects are explicit. Review-gated effects need an approved named reviewer. Each action must use an authority grant assigned to its actor. Required evidence is attached to the event that produced it. Failed mutating effects require a later successful compensation event.

See [`examples/pass.json`](examples/pass.json) for the complete minimal contract.

## Integration

The receipt is plain JSON and can be stored beside an agent trajectory, used as a CI gate, or projected into an evaluation system. It is intentionally runtime-neutral: the events can originate in business applications, browser automation, API agents, durable workflows, or a custom environment.

## Commercial use

The CLI is MIT licensed. Bonfyre offers a bounded **Agent Workflow Safety Audit** for teams that want their own trace schema, authority model, effect taxonomy, replay checks, and CI integration mapped into this verifier. The initial audit is offered at **$1,500 USD** for one workflow and one integration target; scope and availability are confirmed before work begins.

Start with the structured [Agent Workflow Safety Audit intake](https://github.com/Nickgonzales76017/bonfyre-agent-trace-verifier/issues/new?template=agent-workflow-safety-audit.yml). Do not include credentials, private traces, customer data, or other sensitive material. The intake confirms fit and scope only; no work or payment is accepted until both sides agree on the delivery boundary.

For environment and RL/evaluation teams, the repository also includes a [synthetic Helpdesk SLA environment](environments/helpdesk_sla/README.md) with deterministic reset, isolated branching, JSON replay, explicit authority/effect boundaries, and the same eight verifier dimensions. A fixed-scope one-workflow environment projection pilot is listed at **$2,500 USD** through the [environment pilot intake](https://github.com/Nickgonzales76017/bonfyre-agent-trace-verifier/issues/new?template=frappe-helpdesk-environment-pilot.yml).

## Limits

This verifier checks declared traces; it does not prove that an event source is truthful. Production deployments should sign receipts, bind event identities to the source system, and preserve append-only evidence.

## License

MIT. See [LICENSE](LICENSE).

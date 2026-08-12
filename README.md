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

## Try it

```bash
python3 verifier.py examples/pass.json
python3 verifier.py examples/fail.json  # exits 1 and explains each failed dimension
python3 -m unittest discover -s tests -v
```

Passing traces exit `0`, policy failures exit `1`, and malformed inputs exit `2`.

## Trace contract

Each trace declares the task envelope, policy, ordered events, and observed outcomes. Effects are explicit. Review-gated effects need an approved named reviewer. Each action must use an authority grant assigned to its actor. Required evidence is attached to the event that produced it. Failed mutating effects require a later successful compensation event.

See [`examples/pass.json`](examples/pass.json) for the complete minimal contract.

## Integration

The receipt is plain JSON and can be stored beside an agent trajectory, used as a CI gate, or projected into an evaluation system. It is intentionally runtime-neutral: the events can originate in Frappe, browser automation, API agents, durable workflows, or a custom environment.

## Commercial use

The CLI is MIT licensed. Bonfyre offers a bounded **Agent Workflow Safety Audit** for teams that want their own trace schema, authority model, effect taxonomy, replay checks, and CI integration mapped into this verifier. The initial audit is offered at **$1,500 USD** for one workflow and one integration target; scope and availability are confirmed before work begins.

Contact: open a GitHub issue in this repository with the title `Agent Workflow Safety Audit` and no sensitive data.

## Limits

This verifier checks declared traces; it does not prove that an event source is truthful. Production deployments should sign receipts, bind event identities to the source system, and preserve append-only evidence.

## License

MIT. See [LICENSE](LICENSE).

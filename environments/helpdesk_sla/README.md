# Synthetic Helpdesk SLA environment

This is a compact, deterministic projection of a Helpdesk ticket-resolution task. It uses recognizable ticket, team, SLA, assignment, customer-message, and closure semantics without calling a live Frappe site or containing customer data.

The environment exposes:

- reset to an identical content-addressed state;
- isolated branches for candidate trajectories;
- an explicit action and authority contract;
- review-gated external messaging;
- version receipts for every mutating effect;
- replay from a JSON action sequence;
- a trace consumable by the repository verifier;
- separate task, semantic, effect, authority, evidence, recovery, efficiency, and cost results.

Run the reference trajectory and verify its emitted trace:

```bash
python3 environments/helpdesk_sla/environment.py > /tmp/helpdesk-run.json
python3 -c 'import json; p=json.load(open("/tmp/helpdesk-run.json")); json.dump(p["trace"], open("/tmp/helpdesk-trace.json", "w"))'
python3 verifier.py /tmp/helpdesk-trace.json
python3 -m unittest discover -s tests -v
```

The fixture is synthetic and demonstrates a contract boundary, not live Frappe integration or production adoption.

## Fixed-scope environment pilot

Bonfyre offers a **$2,500 USD** pilot to project one public or synthetic workflow into the same reset/branch/replay and multidimensional-verifier boundary. It includes one task, one integration target, safe and unsafe trajectories, tests, and a checksummed evidence bundle. Production deployment, private data handling, hosting, and compliance claims are excluded; scope, payment, and acceptance criteria are agreed before work.

Start with the [environment pilot intake](../../.github/ISSUE_TEMPLATE/frappe-helpdesk-environment-pilot.yml). Do not post credentials, private traces, customer data, or proprietary schemas.

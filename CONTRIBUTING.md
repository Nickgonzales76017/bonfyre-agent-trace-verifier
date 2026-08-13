# Contributing

Use a focused branch and pull request. Describe the defect or interoperability
need, keep trace fixtures free of credentials and private data, and add or
update an automated test for behavior changes.

Before opening a pull request, run:

```bash
python3 -m unittest discover -s tests -v
```

Use [GitHub issues](https://github.com/Nickgonzales76017/bonfyre-agent-trace-verifier/issues)
for public defect reports and design discussion. Use the private channel in
[SECURITY.md](SECURITY.md) for suspected vulnerabilities.

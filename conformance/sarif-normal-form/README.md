# SARIF result identity under Unicode normal form and line endings

A standalone, standard-library-only reproduction showing that SARIF result
fingerprints are not invariant under two encoding differences that carry no
behavioural meaning:

1. the Unicode normal form of a filename (NFC vs NFD), and
2. the line-ending convention of a source snippet (LF vs CRLF).

```
python3 repro_normal_form_fingerprints.py
```

Exit code is 0 when the reproduction behaves as described.

## What it shows

| Fingerprint inputs canonicalized | Distinct fingerprints for one logical finding |
| --- | --- |
| not at all | 3 |
| after the IRI-to-URI mapping | 2 (insufficient) |
| before the IRI-to-URI mapping | 1 (correct) |

## Why the ordering is the load-bearing part

The SARIF v2.2 working draft requires a producer to transform an IRI into a URI
using the RFC 3987 mapping before assigning it to a URI-valued property. That
mapping is UTF-8 percent-encoding, and percent-encoding is *normal-form
preserving*:

```
NFC "ö"  ->  %C3%B6
NFD "ö"  ->  o%CC%88
```

Both outputs are conformant. Once the mapping has run, the distinction has been
frozen into ASCII percent-triplets, and applying NFC to the resulting string is
a no-op — there is no longer a combining character for it to fold. So the
intuitive remedy ("normalize the strings you hash") does not work if it is
applied to the finished URI.

Canonicalization has to be a *precondition* of the IRI-to-URI transformation,
not a property asserted about the final string.

## Relationship to this repository

`verifier.py` applies `canonical_text()` — NFC plus a line-ending fold — to
trace text and to dictionary keys before computing the canonical digest, and
records `CANONICALIZATION_VERSION` alongside the digest so that two runs are
only ever compared when they canonicalized the same way. This reproduction
isolates the same property in SARIF's vocabulary so it can be discussed
independently of this implementation.

## Upstream

Filed with the OASIS SARIF TC for consideration in SARIF 2.2.

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
| NFC applied directly to the mapped URI | 2 (insufficient) |
| mapped path decoded, normalized, and re-encoded | 1 (sufficient) |
| before the IRI-to-URI mapping | 1 (sufficient) |

## Why the canonicalization surface is the load-bearing part

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

Percent-encoding is reversible, however. A producer can also repair the mapped
path by decoding its UTF-8 percent sequences, applying NFC, and re-encoding it.
The reproduction demonstrates both sufficient placements. It deliberately does
not claim that pre-mapping normalization is the only possible repair: a general
post-mapping URI canonicalizer must operate component by component and preserve
reserved-character semantics, but that is a larger contract than applying NFC
to the final ASCII string.

## Relationship to this repository

`verifier.py` applies `canonical_text()` — NFC plus a line-ending fold — to
trace text and to dictionary keys before computing the canonical digest, and
records `CANONICALIZATION_VERSION` alongside the digest so that two runs are
only ever compared when they canonicalized the same way. This reproduction
isolates the same property in SARIF's vocabulary so it can be discussed
independently of this implementation.

## Upstream

Filed with the OASIS SARIF TC for consideration in SARIF 2.2.

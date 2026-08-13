#!/usr/bin/env python3
"""Reproduction: SARIF result identity is not invariant under Unicode normal form
or line-ending convention.

Standard library only. Python 3.8+. Run:  python3 repro_normal_form_fingerprints.py

Context
-------
SARIF v2.2 working draft, "Internationalized Resource Identifiers (IRIs)":

    If a URI-valued property refers to a resource identified by an IRI, the SARIF
    producer SHALL first transform the IRI into a URI, using the mapping mechanism
    specified in RFC 3987 [...] describes how to replace such characters with
    "percent-encoded" equivalents to produce a valid URI.

The RFC 3987 IRI-to-URI mapping is UTF-8 percent-encoding. It is *normal-form
preserving*: it does not fold canonically equivalent sequences together. So the
same logical filename yields two different conformant `artifactLocation.uri`
values depending on the producing platform's Unicode normal form.

The spec already records the line-ending half of this problem, but only as a NOTE
attached to root-element `guid` sameness, not to result identity:

    NOTE 3: Hashing of text based formats is ambiguous for duplicate detection as
    the line ending conventions differ and impact the hash.

Neither the `fingerprints` nor the `partialFingerprints` section states any
canonicalization requirement for the strings that feed a fingerprint.

This script demonstrates both halves, an insufficient direct-URI normalization,
and two sufficient repairs.
"""
from __future__ import annotations

import hashlib
import json
import unicodedata
import urllib.parse

# --------------------------------------------------------------------------
# Case A: Unicode normal form of a filename
# --------------------------------------------------------------------------
# "sör.txt" -- the spec's own EXAMPLE 1 filename from the IRI section.
NAME_NFC = unicodedata.normalize("NFC", "sör.txt")   # o-with-diaeresis, composed
NAME_NFD = unicodedata.normalize("NFD", "sör.txt")   # o + U+0308 combining

BASE = "https://www.example.com/hu/"


def iri_to_uri(iri: str) -> str:
    """RFC 3987 IRI-to-URI mapping: UTF-8 percent-encode non-URI characters.

    This is what the SARIF v2.2 draft requires a producer to do. It is applied
    verbatim, with no normalization step, because the spec does not ask for one.
    """
    return urllib.parse.quote(iri, safe="/:@!$&'()*+,;=~-._")


# --------------------------------------------------------------------------
# Case B: line endings inside a fingerprint input
# --------------------------------------------------------------------------
SNIPPET_LF = "def check(x):\n    return x is None\n"
SNIPPET_CRLF = SNIPPET_LF.replace("\n", "\r\n")


def partial_fingerprint(uri: str, snippet: str, rule_id: str) -> str:
    """A representative producer-side partialFingerprint.

    Hashes the artifact URI, the region snippet, and the rule id -- exactly the
    inputs Appendix B and the issue #122 discussion contemplate. No
    canonicalization, because the spec requires none.
    """
    payload = json.dumps(
        {"uri": uri, "snippet": snippet, "ruleId": rule_id},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


# --------------------------------------------------------------------------
# The proposed canonicalization
# --------------------------------------------------------------------------
def canonical_text(text: str) -> str:
    """NFC + line-ending fold. Repairs normal form rather than rejecting it."""
    text = unicodedata.normalize("NFC", text)
    return text.replace("\r\n", "\n").replace("\r", "\n")


def canonicalize_mapped_uri_path(uri: str) -> str:
    """Decode, normalize, and re-encode the mapped URI's path component.

    Percent-encoding is reversible. This path-scoped function is sufficient for
    the reproduction and avoids claiming that pre-mapping normalization is the
    only repair. A general URI canonicalizer must handle each component and its
    reserved-character rules separately.
    """
    parts = urllib.parse.urlsplit(uri)
    decoded_path = urllib.parse.unquote(parts.path, encoding="utf-8", errors="strict")
    normalized_path = iri_to_uri(canonical_text(decoded_path))
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, normalized_path, parts.query, parts.fragment)
    )


def main() -> int:
    print("=" * 74)
    print("SARIF result identity vs Unicode normal form and line endings")
    print("=" * 74)

    # ---- Case A ----------------------------------------------------------
    uri_nfc = iri_to_uri(BASE + NAME_NFC)
    uri_nfd = iri_to_uri(BASE + NAME_NFD)

    print("\nCASE A -- same file, two platforms, two conformant URIs")
    print(f"  NFC filename codepoints : {[hex(ord(c)) for c in NAME_NFC]}")
    print(f"  NFD filename codepoints : {[hex(ord(c)) for c in NAME_NFD]}")
    print(f"  NFC -> uri : {uri_nfc}")
    print(f"  NFD -> uri : {uri_nfd}")
    print(f"  URIs equal : {uri_nfc == uri_nfd}")
    print("  Both are valid RFC 3987 mappings. The spec mandates the mapping")
    print("  but not the normal form, so both producers conform.")

    fp_a1 = partial_fingerprint(uri_nfc, SNIPPET_LF, "NULL_DEREF")
    fp_a2 = partial_fingerprint(uri_nfd, SNIPPET_LF, "NULL_DEREF")
    print(f"\n  partialFingerprint (NFC) : {fp_a1}")
    print(f"  partialFingerprint (NFD) : {fp_a2}")
    print(f"  MATCH                    : {fp_a1 == fp_a2}   <-- same finding, unmatched")

    # ---- Case B ----------------------------------------------------------
    print("\nCASE B -- same source line, two checkout conventions")
    fp_b1 = partial_fingerprint(uri_nfc, SNIPPET_LF, "NULL_DEREF")
    fp_b2 = partial_fingerprint(uri_nfc, SNIPPET_CRLF, "NULL_DEREF")
    print(f"  partialFingerprint (LF)   : {fp_b1}")
    print(f"  partialFingerprint (CRLF) : {fp_b2}")
    print(f"  MATCH                     : {fp_b1 == fp_b2}   <-- same finding, unmatched")
    print("  Trigger: git core.autocrlf=true on Windows checkouts.")

    # ---- Combined --------------------------------------------------------
    print("\nCASE A+B -- macOS producer vs Windows producer")
    fp_c1 = partial_fingerprint(uri_nfd, SNIPPET_LF, "NULL_DEREF")
    fp_c2 = partial_fingerprint(uri_nfc, SNIPPET_CRLF, "NULL_DEREF")
    print(f"  MATCH : {fp_c1 == fp_c2}")

    # ---- Insufficient fix: apply NFC directly to the mapped URI ----------
    # This is the obvious reading of "normalize your fingerprint inputs", and
    # it does NOT work. Percent-encoding has already frozen the combining
    # character into ASCII bytes ("o%CC%88"), so NFC has nothing left to fold.
    print("\nINSUFFICIENT FIX -- apply NFC directly to the mapped URI")
    variants = [
        ("NFC / LF  ", uri_nfc, SNIPPET_LF),
        ("NFD / LF  ", uri_nfd, SNIPPET_LF),
        ("NFC / CRLF", uri_nfc, SNIPPET_CRLF),
        ("NFD / CRLF", uri_nfd, SNIPPET_CRLF),
    ]
    fps_direct = []
    for label, uri, snip in variants:
        fp = partial_fingerprint(canonical_text(uri), canonical_text(snip), "NULL_DEREF")
        fps_direct.append(fp)
        print(f"  {label} -> {fp}")
    direct_ok = len(set(fps_direct)) == 1
    print(f"  All four agree : {direct_ok}   <-- still broken")
    print("  NFC('so%CC%88r.txt') == 'so%CC%88r.txt'. The encoding is already ASCII;")
    print("  the normal-form distinction survives as literal percent-triplets.")

    # ---- Sufficient post-mapping repair: decode, NFC, re-encode -----------
    print("\nSUFFICIENT FIX A -- decode, normalize, and re-encode the mapped path")
    fps_roundtrip = []
    for label, uri, snip in variants:
        canonical_uri = canonicalize_mapped_uri_path(uri)
        fp = partial_fingerprint(canonical_uri, canonical_text(snip), "NULL_DEREF")
        fps_roundtrip.append(fp)
        print(f"  {label} -> {fp}")
    roundtrip_ok = len(set(fps_roundtrip)) == 1
    print(f"  All four agree : {roundtrip_ok}")

    # ---- Sufficient pre-mapping repair: NFC, then map --------------------
    print("\nSUFFICIENT FIX B -- canonicalize BEFORE the IRI-to-URI mapping")
    fps_before = []
    for label, name, snip in [
        ("NFC / LF  ", NAME_NFC, SNIPPET_LF),
        ("NFD / LF  ", NAME_NFD, SNIPPET_LF),
        ("NFC / CRLF", NAME_NFC, SNIPPET_CRLF),
        ("NFD / CRLF", NAME_NFD, SNIPPET_CRLF),
    ]:
        uri = iri_to_uri(canonical_text(BASE + name))
        fp = partial_fingerprint(uri, canonical_text(snip), "NULL_DEREF")
        fps_before.append(fp)
        print(f"  {label} -> {fp}")
    before_ok = len(set(fps_before)) == 1
    print(f"  All four agree : {before_ok}")

    print("\n" + "=" * 74)
    print("RESULT")
    print("=" * 74)
    distinct_without = len({fp_a1, fp_a2, fp_b2, fp_c1, fp_c2})
    print(f"  No canonicalization        : {distinct_without} distinct fingerprints for 1 logical finding")
    print(f"  NFC on mapped URI          : {len(set(fps_direct))} distinct fingerprints  (INSUFFICIENT)")
    print(f"  Decode/NFC/re-encode path  : {len(set(fps_roundtrip))} distinct fingerprint   (SUFFICIENT)")
    print(f"  NFC before mapping         : {len(set(fps_before))} distinct fingerprint   (SUFFICIENT)")
    print("\n  Percent-encoding does NOT fold normal form:")
    print(f"    NFC 'o-umlaut' -> {urllib.parse.quote(unicodedata.normalize('NFC', 'ö'))}")
    print(f"    NFD 'o-umlaut' -> {urllib.parse.quote(unicodedata.normalize('NFD', 'ö'))}")
    print("\n  Applying NFC directly to the finished ASCII URI is insufficient.")
    print("  Percent-encoding is reversible, so component-aware decode/NFC/re-encode")
    print("  works too. A specification can require either sufficient placement;")
    print("  it must not imply that NFC over the mapped URI string itself is enough.")
    return 0 if (before_ok and roundtrip_ok and not direct_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())

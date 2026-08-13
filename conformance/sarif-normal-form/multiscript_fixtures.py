#!/usr/bin/env python3
"""Multi-script fixture table for SARIF fingerprint normal-form sensitivity.

Companion to repro_normal_form_fingerprints.py. Standard library only.

The single-character "sör.txt" case is the smallest demonstration, but it
understates the problem. This table measures, per writing system, how far apart
the NFC and NFD forms of a realistic filename actually are after the RFC 3987
IRI-to-URI mapping that SARIF requires.

The point is that the divergence is not a Latin-diacritic curiosity. For Korean
Hangul, every syllable decomposes, so a short filename can differ in almost
every byte of its percent-encoded form while naming the same file.

    python3 multiscript_fixtures.py
"""
from __future__ import annotations

import unicodedata
import urllib.parse

SAFE = "/:@!$&'()*+,;=~-._"

# (label, filename) -- realistic names, not synthetic edge cases.
FIXTURES = [
    ("Latin / German", "größe-prüfung.txt"),
    ("Latin / French", "résumé-café.txt"),
    ("Latin / Vietnamese", "kiểm-tra-tiếng-việt.txt"),
    ("Latin / Czech", "příliš-žluťoučký.txt"),
    ("Korean / Hangul", "한국어-테스트.txt"),
    ("Devanagari / Hindi", "परीक्षण-फ़ाइल.txt"),
    ("Greek", "δοκιμή-αρχείο.txt"),
    ("Cyrillic / Russian", "тест-файл.txt"),
    ("Japanese / kana with dakuten", "がぎぐげご-ばびぶべぼ.txt"),
    ("Arabic", "اختبار-ملف.txt"),
]


def enc(s: str) -> str:
    return urllib.parse.quote(s, safe=SAFE)


def main() -> int:
    print("Divergence between NFC and NFD forms after the RFC 3987 mapping")
    print("=" * 78)
    print(f"{'script':<32}{'cp NFC':>7}{'cp NFD':>7}{'enc NFC':>9}{'enc NFD':>9}  differs")
    print("-" * 78)

    diverging = 0
    for label, name in FIXTURES:
        nfc = unicodedata.normalize("NFC", name)
        nfd = unicodedata.normalize("NFD", name)
        e_nfc, e_nfd = enc(nfc), enc(nfd)
        differs = e_nfc != e_nfd
        diverging += differs
        print(f"{label:<32}{len(nfc):>7}{len(nfd):>7}{len(e_nfc):>9}{len(e_nfd):>9}  {'YES' if differs else 'no'}")

    print("-" * 78)
    print(f"{diverging} of {len(FIXTURES)} scripts produce two different conformant URIs")

    # Worst case, spelled out.
    label, name = "Korean / Hangul", "한국어-테스트.txt"
    nfc = unicodedata.normalize("NFC", name)
    nfd = unicodedata.normalize("NFD", name)
    print(f"\nWorst case -- {label}")
    print(f"  NFC : {enc(nfc)}")
    print(f"  NFD : {enc(nfd)}")
    print(f"  percent-encoded length {len(enc(nfc))} vs {len(enc(nfd))}")
    print("  Same filename. Both conformant. No shared prefix beyond the scheme.")

    print("\nScripts where NFC and NFD coincide (Devanagari and Arabic here) are not")
    print("safe either -- they are simply cases where these particular characters have")
    print("no canonical decomposition. A producer cannot know in advance which inputs")
    print("are affected, which is why the constraint belongs in the spec rather than in")
    print("per-tool judgement.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

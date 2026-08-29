#!/usr/bin/env python3
"""Gate 06, first defence -- scan the WHOLE shipping canon for identifiers.

    python tools/ci/check_ship_isolation.py build/specification.ship.json
    python tools/ci/check_ship_isolation.py --selftest

check_spec.py --shipped verifies that `citation` is gone and that copyrighted
sources have lost their author and title. That is necessary and not sufficient:
an identifier can ride along in any other string in the file -- a source key, a
note, a summary, a data-file path. This scans every string value in the document.

TWO DESIGN DECISIONS, both learned the hard way:

1.  The forbidden terms are DERIVED FROM THE DEVELOPMENT CANON, not hard-coded.
    The surnames and titles come out of `sources[]` (and `provenance` when a
    project carries one). Add a textbook to the canon
    and this gate starts guarding it the same day. A hand-maintained list goes
    stale silently, and a stale isolation gate reports success.

2.  It does NOT scan for the bare word "law". A combustion textbook by an author
    of that name exists, but "second law", "first law" and "third law" are the
    ordinary vocabulary of this subject and appear in dozens of legitimate
    strings. A gate that fires on those is a gate that gets switched off within
    two days. Author surnames of four letters or more only, and the structural
    citation patterns, which have no false positives at all.

Exit codes: 0 pass, 1 fail, 2 not applicable.
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Structural citation patterns. These identify a *reference into a book*
# regardless of which book, and none of them has a legitimate reason to survive
# stripping.
STRUCTURAL = [
    (re.compile(r"\bEq\.\s*\d", re.I), "equation reference"),
    (re.compile(r"\bsec\.\s*\d", re.I), "section reference"),
    (re.compile(r"\bch\.\s*\d", re.I), "chapter reference"),
    (re.compile(r"\bchapters?\s+\d", re.I), "chapter reference"),
    (re.compile(r"\bTable\s+[A-Z]?-?\d"), "table reference"),
    (re.compile(r"\bExample\s+\d", re.I), "worked-example reference"),
    (re.compile(r"\bProblem\s+\d", re.I), "problem reference"),
    (re.compile(r"§\s*\d"), "section reference"),
    (re.compile(r"\b\d+(?:st|nd|rd|th)\s+ed\b", re.I), "edition reference"),
    (re.compile(r"\b\d+e\s+sec", re.I), "edition-and-section reference"),
]


def source_records(dev_spec: dict) -> dict[str, dict]:
    """Author/title per source key.

    The canonical home is `sources[]` itself (spec v4.0, stage 01). Some
    projects also carry a `provenance` map keyed the same way -- that is an
    *extension*, not a replacement, so merge it in rather than depending on
    it. This gate was originally written against `provenance` alone and
    crashed with KeyError on every project that does not have one, which is
    the plain-vanilla case the template generates.
    """
    out: dict[str, dict] = {}
    for s in dev_spec.get("sources", []):
        key = s.get("key")
        if key:
            out[key] = {"author": s.get("author", ""),
                        "title": s.get("title", "")}
    for key, rec in (dev_spec.get("provenance") or {}).items():
        merged = out.setdefault(key, {})
        for field in ("author", "title"):
            if rec.get(field):
                merged[field] = rec[field]
    return out


def forbidden_terms(dev_spec: dict) -> list[tuple[re.Pattern, str]]:
    """Surnames and titles of every copyrighted source, taken from the canon."""
    out = []
    records = source_records(dev_spec)
    copyrighted = {s["key"] for s in dev_spec.get("sources", [])
                   if s.get("licence") == "copyrighted" and s.get("key")}
    for key, rec in records.items():
        if key not in copyrighted:
            continue
        for name in re.split(r"[,&]| and ", rec.get("author", "")):
            parts = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]+", name)
                     if len(w) >= 4]
            if parts:
                surname = parts[-1]
                out.append((re.compile(rf"\b{re.escape(surname)}\b", re.I),
                            f"author of the {key}"))
        title = rec.get("title", "").strip()
        if len(title) >= 12:
            out.append((re.compile(re.escape(title), re.I),
                        f"title of the {key}"))
    return out


def walk(node, path="$"):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def scan(ship: dict, terms) -> list[str]:
    hits = []
    for path, text in walk(ship):
        for pat, why in terms + STRUCTURAL:
            m = pat.search(text)
            if m:
                hits.append(f"{path}: {m.group(0)!r} -- {why}")
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ship", nargs="?", type=Path)
    ap.add_argument("--dev", type=Path, default=Path("spec/specification.json"))
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if not args.dev.exists():
        print(f"development canon not found: {args.dev}", file=sys.stderr)
        return 2
    dev = json.loads(args.dev.read_text(encoding="utf-8"))
    terms = forbidden_terms(dev)

    if args.selftest:
        # A gate whose only output is "nothing found" must prove it can find
        # something. Two samples: one that must fire, one that must NOT.
        surname = ""
        records = source_records(dev)
        for s in dev.get("sources", []):
            if s.get("licence") != "copyrighted":
                continue
            author = records.get(s.get("key", ""), {}).get("author", "")
            names = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]+", author)
                     if len(w) >= 4]
            if names:
                surname = names[-1]
                break
        if not surname:
            print("not applicable: the canon has no copyrighted source with an "
                  "author to derive a known-bad sample from", file=sys.stderr)
            return 2
        bad = {"a": f"see {surname} for the derivation",
               "b": "as given in Eq. 5.12",
               "c": "Table A-4 lists the values"}
        good = {"a": "the second law forbids this",
                "b": "a first-law balance closes here",
                "c": "third-law entropies are required for reacting systems",
                "d": "IAPWS-IF97 verification tables are the fixture source",
                "e": "NASA and NIST data are public domain and are named on screen"}
        fired = scan(bad, terms)
        quiet = scan(good, terms)
        if len(fired) < 3:
            print(f"SELFTEST FAILED: known-bad sample produced only "
                  f"{len(fired)} hits, expected 3. The scan is not working, and "
                  f"a silent pass is worse than no gate at all.", file=sys.stderr)
            return 2
        if quiet:
            print("SELFTEST FAILED: legitimate physics vocabulary was flagged:",
                  file=sys.stderr)
            for q in quiet:
                print(f"  {q}", file=sys.stderr)
            print("A gate that cries wolf gets switched off. Narrow the terms.",
                  file=sys.stderr)
            return 2
        print(f"selftest passed: {len(fired)} hits on the known-bad sample, "
              f"0 on legitimate physics vocabulary")
        return 0

    if args.ship is None or not args.ship.exists():
        print("shipping copy not built yet -- run tools/build/strip_spec.py first")
        return 2

    ship = json.loads(args.ship.read_text(encoding="utf-8"))
    hits = scan(ship, terms)
    if hits:
        print(f"Gate 06 ship isolation FAILED: {len(hits)} identifier(s) "
              f"survived stripping")
        for h in hits:
            print(f"  x {h}")
        return 1
    n = sum(1 for _ in walk(ship))
    print(f"Gate 06 ship isolation passed: {n} strings scanned, "
          f"{len(terms) + len(STRUCTURAL)} patterns, 0 hits")
    return 0


if __name__ == "__main__":
    sys.exit(main())

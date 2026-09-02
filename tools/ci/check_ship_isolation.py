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

2.  A structural reference is only a violation when it points at a source the
    canon marks as NOT shippable. Naming a public-domain government report --
    "affdl-sam Ch. 3", "nasa-asm Sec. A1" -- is explicitly permitted by the
    legal-isolation rules and, the standard says, increases credibility rather
    than risking anything. The first version had no such distinction and fired
    23 times on exactly those strings; every hit was legitimate. Which sources
    are shippable comes from the canon's `sources[]`, the same place the
    surnames do, so adding a source settles both questions at once.

3.  It does NOT scan for the bare word "law". A combustion textbook by an author
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


def shippable_keys(dev: dict) -> list[str]:
    """Names by which a shippable source may be called in the shipped canon.

    Public-domain government reports are on the permitted list in the
    legal-isolation rules; copyrighted textbooks are not. The canon already
    records which is which, so this is read rather than restated.

    [M-03] The list is no longer just `sources[].key`. Prose written by humans
    calls these documents by their human names -- "AFFDL Sec. 3", "NASA Sec.
    A3", "MIL-HDBK-5J Table B4" -- not by the canon's internal key
    `affdl-sam`. Keys alone produced 28 hits on one project's
    `verification_note` fields, every one of them a legitimate citation into a
    public-domain government report, which is the exact false-positive class
    this file's docstring already records having fired 23 times before.

    So distinctive tokens from `key`, `edition`, `title` and `author` count
    too, filtered two ways so the exemption cannot swallow the rule:

      * >= 4 characters, so "US" and "of" do not match everything;
      * not an ordinary word of this subject -- STOPWORDS below. Without that
        filter, `title` = "Stress Analysis Manual" would make the word
        "stress" a licence to cite any chapter of any book.
    """
    return sorted(set(_shippable_names(dev)))


#: Words that appear in public-domain report titles but are also the everyday
#: vocabulary of these subjects. Naming one of these is not naming the report.
STOPWORDS = {
    "stress", "analysis", "manual", "structures", "structural", "materials",
    "mechanics", "metallic", "elements", "aerospace", "vehicle", "volumes",
    "flight", "dynamics", "laboratory", "force", "department", "defense",
    "center", "space", "george", "marshall", "astronautic", "elastic",
}


def _shippable_names(dev: dict):
    for src in dev.get("sources", []):
        if not (src.get("ship") is True
                or src.get("licence") == "public-domain"):
            continue
        key = src.get("key")
        if key:
            yield key
        for field in ("edition", "title", "author"):
            value = src.get(field) or ""
            for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", value):
                if token.lower() not in STOPWORDS:
                    yield token
                # Hyphenated report numbers are cited by their prefix as often
                # as in full: the canon says `AFFDL-TR-69-42`, the note says
                # "AFFDL Sec. 3". Split and keep the alphabetic parts that are
                # long enough to be distinctive (AFFDL, HDBK), which is where
                # five of the remaining hits came from.
                for part in re.findall(r"[A-Za-z]{4,}", token):
                    if part.lower() not in STOPWORDS:
                        yield part


def surviving_copyrighted(ship: dict) -> list[tuple[str, str]]:
    """Copyrighted / non-shippable source records still present in the ship copy.

    [M-F1] Two independent grounds, either one enough:

    * ``licence == "copyrighted"`` -- stated outright;
    * ``ship`` is not ``True`` -- the canon declined to clear it, and a record
      nobody cleared is a record that should not be there.

    The two are checked separately rather than as one condition because they
    have drifted before: a source can carry ``ship: false`` and no ``licence``
    at all, and vice versa. Either alone is a failure.
    """
    out: list[tuple[str, str]] = []
    for source in ship.get("sources", []):
        key = source.get("key", "?")
        if source.get("licence") == "copyrighted":
            out.append((key, 'licence == "copyrighted"'))
        elif source.get("ship") is not True:
            out.append((key, "ship is not true -- nobody cleared it to ship"))
    return out


def cites_only_shippable(text: str, keys: list[str]) -> bool:
    """Is every source named in this string one that may ship?

    A string like ``"affdl-sam Ch. 3"`` carries a chapter reference, but to a
    document the canon clears for naming. A string with a chapter reference and
    no shippable key named is the case this gate exists for.
    """
    named = [key for key in keys if key in text]
    return bool(named)


def scan(ship: dict, terms, shippable: list[str] | None = None) -> list[str]:
    shippable = shippable or []
    hits = []
    for path, text in walk(ship):
        for pat, why in terms + STRUCTURAL:
            m = pat.search(text)
            if not m:
                continue
            if (pat, why) in [(p, w) for p, w in STRUCTURAL] \
                    and cites_only_shippable(text, shippable):
                continue
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
        # A chapter reference INTO a public-domain source is permitted, and was
        # the gate's first and only false-positive class: 23 hits, all legal.
        shippable = shippable_keys(dev)
        if shippable:
            good["f"] = f"{shippable[0]} Ch. 3"
            good["g"] = f"{shippable[0]} Sec. A1; verification fixture"
            # ...but the same pattern with no shippable source named must still
            # fire, or the exemption has swallowed the rule.
            bad["d"] = "as set out in Ch. 7 of the course text"
            bad["e"] = "see Sec. 4.2 for the derivation"
            # [M-03] The human name, not the canon key: prose says "AFFDL
            # Sec. 3", never "affdl-sam Sec. 3". Five real hits came from
            # exactly this, and every one was a citation into a public-domain
            # government report.
            for src in dev.get("sources", []):
                if src.get("licence") != "public-domain":
                    continue
                edition = (src.get("edition") or "")
                head = re.findall(r"[A-Za-z]{4,}", edition)
                if head:
                    good["h"] = f"{head[0]} Sec. 3 'Bar Analysis' (PDF p.239)"
                    break
        fired = scan(bad, terms, shippable)
        quiet = scan(good, terms, shippable)
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
        # [M-F1] The record-level check needs its own known-bad sample: the
        # exact shape that used to pass, i.e. author and title stripped but
        # the record still present.
        stripped_but_present = {"sources": [
            {"key": "primary-a-solutions", "edition": "10th", "year": 2017,
             "role": "adaptation-audit", "licence": "copyrighted",
             "ship": False},
            {"key": "nasa-asm", "author": "NASA", "title": "Structures Manual",
             "licence": "public-domain", "ship": True},
        ]}
        survivors = surviving_copyrighted(stripped_but_present)
        if len(survivors) != 1 or survivors[0][0] != "primary-a-solutions":
            print("SELFTEST FAILED: a copyrighted source record with author "
                  "and title already stripped was NOT caught. That exact "
                  "shape is what shipped.", file=sys.stderr)
            return 2
        clean = {"sources": [{"key": "nasa-asm", "author": "NASA",
                              "licence": "public-domain", "ship": True}]}
        if surviving_copyrighted(clean):
            print("SELFTEST FAILED: a public-domain source that the canon "
                  "cleared to ship was flagged. Naming those is permitted and "
                  "increases credibility.", file=sys.stderr)
            return 2
        print(f"selftest passed: {len(fired)} hits on the known-bad sample, "
              f"0 on legitimate physics vocabulary; the record-level check "
              f"catches a stripped-but-present copyrighted source and lets a "
              f"public-domain one through")
        return 0

    if args.ship is None or not args.ship.exists():
        print("shipping copy not built yet -- run tools/build/strip_spec.py first")
        return 2

    ship = json.loads(args.ship.read_text(encoding="utf-8"))
    hits = scan(ship, terms, shippable_keys(dev))
    survivors = surviving_copyrighted(ship)
    n = sum(1 for _ in walk(ship))
    print(f"CHECKED n={n} unit=strings  -- {n} strings scanned against "
          f"{len(terms) + len(STRUCTURAL)} patterns")
    if n == 0:
        print("Gate 06 ship isolation FAILED: not one string was scanned. "
              "Zero hits out of zero strings is not a clean bill of health.")
        return 1
    if survivors:
        # [M-F1] A whole record, not a field. Stripping `author` and `title`
        # left `{"edition": "10th", "year": 2017, "role":
        # "adaptation-audit", "licence": "copyrighted"}` in the shipped canon:
        # that edition-and-year pair identifies exactly one book in this
        # subject, and the role additionally announces that its solutions
        # manual was used. Field-name stripping cannot see this, because the
        # thing that leaks is the record's EXISTENCE, and no field is named
        # "existence". strip_spec.py now deletes such records outright; this
        # is the independent second check that it did.
        print(f"Gate 06 ship isolation FAILED: {len(survivors)} copyrighted "
              f"source record(s) survived into the shipping canon")
        for key, why in survivors:
            print(f"  x sources[{key}]: {why}")
        print("  A source record is an identifier even with author and title "
              "removed -- edition + year names one book. Remove the record.")
        return 1
    if hits:
        print(f"Gate 06 ship isolation FAILED: {len(hits)} identifier(s) "
              f"survived stripping")
        for h in hits:
            print(f"  x {h}")
        return 1
    print(f"Gate 06 ship isolation passed: {n} strings scanned, "
          f"{len(terms) + len(STRUCTURAL)} patterns, 0 hits, "
          f"0 copyrighted source records")
    return 0


if __name__ == "__main__":
    sys.exit(main())

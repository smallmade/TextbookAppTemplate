#!/usr/bin/env python3
"""Gate: the **transcribed** fixtures obey the adjudication discipline.

Two layers are transcribed off a printed page rather than computed -- layer 1's
printed tables and layer 5's independent second source -- and both need the same
paperwork, for the same reason. The file keeps its name because runners across
the app series already call it.

Layer 5 is the only verification layer independent of the primary textbooks,
which is exactly why it is the one that can quietly do damage.  When a layer-5
row disagrees with the kernel, the tempting move is to change the kernel -- the
fixture is, after all, the "independent" one.  But a second source is
independent, not infallible: of the first seven values this project transcribed
from a public-domain manual, two were wrong on the printed page.

So a disagreement must be **adjudicated in writing, on grounds independent of
both sides**, before it becomes an assertion.  This gate checks that the
paperwork is actually there:

  L5-0  both transcribed layers are checked: layer1-printed and
        layer5-secondsource. A printed table is as capable of being wrong as a
        worked example, and on this project both turned out to be: two errors
        in AFFDL's sample problems and two more in its Table 1-14
  L5-1  every fixture sits beside a SOURCE.md
  L5-2  every row declares where it was read: either a page triple, or a
        URL with a retrieval date and the query -- exactly one of the two,
        because a queried database has no page and a fabricated one reads
        as evidence while leading nowhere
  L5-3  every row's verdict is one this discipline recognises
  L5-4  an `agrees` row asserts exactly what the page prints, and cites no
        adjudication -- otherwise the disagreement was resolved silently
  L5-5  a `disputed` row names an adjudication that SOURCE.md actually contains
  L5-6  an optional `printing_fault` column, for the case the verdict vocabulary
        deliberately cannot express: the **value** agrees while the **printed
        working** is wrong. One manual prints a hemispherical head's stress as
        `500(6)/[2(.25)] = 10,000` -- the answer is right for the head's 0.15 in
        thickness and the denominator wrongly repeats the cylinder's. Nothing
        was resolved, so it is not `disputed`; something is wrong, so it should
        not vanish. Its own column, and the key must be in SOURCE.md.

Run with --self-test to prove the gate is alive.  A gate that reports "no
problems found" without ever having been shown a problem is not evidence; this
one is handed six malformed fixtures and must reject every one.
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from pathlib import Path

VERDICTS = {"agrees", "disputed"}

#: Columns every transcribed row needs, whatever it was transcribed from.
REQUIRED = ("module", "tag", "quantity", "unit", "published", "expected",
            "verdict", "adjudication")

#: How a row says where its number came from.  Two forms, because two kinds of
#: source are legitimately in use and only one of them has pages:
#:
#:   paginated  a printed document -- a textbook appendix, a standards release,
#:              a government manual.  Locating it means a page.
#:   retrieved  a queried database -- NIST's WebBook is the one in use here.
#:              There IS no page.  Writing "page 1" to satisfy a schema would be
#:              fabricated provenance, which is worse than none: it reads as
#:              evidence and cannot be followed.
#:
#: Exactly one form must be complete.  Half of each is a typo, and both at once
#: leaves it ambiguous which place the number was actually read from.
LOCATORS = {
    "paginated": ("page_pdf", "page_printed", "section"),
    "retrieved": ("url", "retrieved", "query"),
}

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def read_rows(text: str) -> list[dict[str, str]]:
    """Parse a fixture, skipping the ``#`` provenance header."""
    body = [line for line in io.StringIO(text) if not line.lstrip().startswith("#")]
    return list(csv.DictReader(body))


def check(rows: list[dict[str, str]], source: str, name: str) -> list[str]:
    """Every complaint about one fixture, as human-readable lines."""
    faults: list[str] = []

    def fault(row: dict[str, str], why: str) -> None:
        faults.append(f"{name}: {row.get('tag') or '<no tag>'}: {why}")

    if not rows:
        return [f"{name}: no rows -- a layer that compares nothing is not a layer"]

    for row in rows:
        missing = [field for field in REQUIRED if field not in row]
        if missing:
            fault(row, f"L5-2 missing column(s): {', '.join(missing)}")
            continue

        for field in ("quantity", "unit"):
            if not row[field].strip():
                fault(row, f"L5-2 {field} is empty")

        # L5-2 -- a value nobody can find again is not evidence.  Which fields
        # say "where" depends on what kind of source it was; see LOCATORS.
        present = {}
        for form, fields in LOCATORS.items():
            filled = [f for f in fields if row.get(f, "").strip()]
            if filled:
                present[form] = filled
        if not present:
            fault(row, "L5-2 names no source location at all: give either "
                       f"{'/'.join(LOCATORS['paginated'])} or "
                       f"{'/'.join(LOCATORS['retrieved'])}")
        elif len(present) > 1:
            fault(row, f"L5-2 names {len(present)} kinds of location "
                       f"({', '.join(sorted(present))}); a number is read from "
                       "one place, and two leave it ambiguous which")
        else:
            form = next(iter(present))
            for field in LOCATORS[form]:
                if not row.get(field, "").strip():
                    fault(row, f"L5-2 {form} location is missing {field}")
            if form == "paginated" and not row["page_pdf"].strip().isdigit():
                fault(row, f"L5-2 page_pdf is not a page index: "
                           f"{row['page_pdf']!r}")
            if form == "retrieved":
                when = row["retrieved"].strip()
                if when and not ISO_DATE.match(when):
                    fault(row, f"L5-2 retrieved is not an ISO date: {when!r}")
                where = row["url"].strip()
                if where and not where.startswith(("http://", "https://")):
                    fault(row, f"L5-2 url is not a URL: {where!r}")

        # L5-3 -- an unrecognised verdict is an unadjudicated one.
        verdict = row["verdict"].strip()
        if verdict not in VERDICTS:
            fault(row, f"L5-3 verdict {verdict!r} is not one of "
                       f"{', '.join(sorted(VERDICTS))}")
            continue

        try:
            published = float(row["published"])
            expected = float(row["expected"])
        except ValueError:
            fault(row, "L5-2 published/expected are not numbers")
            continue

        # L5-6 -- a fault in the printed working, with the value agreeing.
        printing = (row.get("printing_fault") or "").strip()
        if printing and printing not in source:
            fault(row, f"L5-6 printing_fault {printing!r} is not in SOURCE.md")

        key = row["adjudication"].strip()
        if verdict == "agrees":
            # L5-4 -- "agrees" must mean agrees.
            if published != expected:
                fault(row, f"L5-4 marked agrees but expected {expected!r} is not "
                           f"the published {published!r}; either it disagrees "
                           f"and must be adjudicated, or the row is wrong")
            if key:
                fault(row, f"L5-4 marked agrees but cites adjudication {key!r}")
        else:
            # L5-5 -- a disputed row without written reasoning is just a
            # disagreement someone resolved in their head.
            if published == expected:
                fault(row, "L5-5 marked disputed but expected equals published")
            if not key:
                fault(row, "L5-5 marked disputed but names no adjudication")
            elif key not in source:
                fault(row, f"L5-5 adjudication {key!r} is not in SOURCE.md")

    return faults


#: The layers whose values are read off a printed page rather than computed.
#: Both carry the same risk -- the page can be wrong -- so both carry the same
#: paperwork. Three directories now: the printed tables of layer 1, the second
#: source of layer 5, and the worked examples of criterion 1b. On this project
#: all three turned out to contain errors -- five in one manual, across sample
#: problems, a printed table, and a worked derivation.
TRANSCRIBED = ("layer5-secondsource", "layer1-printed", "examples")


def gather(root: Path) -> tuple[list[str], int]:
    """Check every transcribed fixture under ``root``."""
    # Two layouts, because this gate was written against one and this project
    # uses the other.  Asked of the tree rather than assumed: a gate that
    # depends on being handed exactly the right path is a gate that will one day
    # be handed the wrong one -- which is how the site gate spent a session
    # reporting five missing pages on a site that was complete.
    roots = (root / "tests" / "data", root / "python" / "tests" / "data")
    data = next((path for path in roots if path.is_dir()), None)
    if data is None:
        return [f"{roots[0]} does not exist"], 0

    faults: list[str] = []
    total = 0
    seen_any = False
    for layer in TRANSCRIBED:
        directory = data / layer
        fixtures = sorted(directory.glob("*.csv")) if directory.is_dir() else []
        if not fixtures:
            continue
        seen_any = True

        # L5-1 -- provenance beside the data, or the data is hearsay.
        source_path = directory / "SOURCE.md"
        if not source_path.is_file():
            faults.append(f"{source_path} is missing")
            continue
        source = source_path.read_text(encoding="utf-8")

        for fixture in fixtures:
            rows = read_rows(fixture.read_text(encoding="utf-8"))
            total += len(rows)
            faults += check(rows, source, f"{layer}/{fixture.name}")

    if not seen_any:
        # Not a failure: an empty transcribed layer is a **stage** a project is
        # openly in, recorded in its charter, and a gate that fails on it every
        # run is a gate that gets ignored. It is a skip with the reason said out
        # loud, which is the third exit code this suite has for exactly this.
        return [], -1
    return faults, total


#: Six fixtures that must each be rejected, and the rule that must catch them.
BAD = [
    ("L5-6", "printing fault with no reason",
     [{"module": "M1", "tag": "t", "page_pdf": "1", "page_printed": "1-2",
       "section": "1.1", "quantity": "q", "unit": "u", "published": "1",
       "expected": "1", "verdict": "agrees", "adjudication": "",
       "printing_fault": "Z-9"}]),
    ("L5-2", "no page", [{"module": "M1", "tag": "t", "page_pdf": "", "page_printed": "1",
                          "section": "1", "quantity": "q", "unit": "u",
                          "published": "1", "expected": "1", "verdict": "agrees",
                          "adjudication": ""}]),
    ("L5-2", "no section", [{"module": "M1", "tag": "t", "page_pdf": "1", "page_printed": "1",
                             "section": "", "quantity": "q", "unit": "u",
                             "published": "1", "expected": "1", "verdict": "agrees",
                             "adjudication": ""}]),
    ("L5-3", "unknown verdict", [{"module": "M1", "tag": "t", "page_pdf": "1",
                                  "page_printed": "1", "section": "1", "quantity": "q",
                                  "unit": "u", "published": "1", "expected": "1",
                                  "verdict": "probably", "adjudication": ""}]),
    ("L5-4", "silent adjudication", [{"module": "M1", "tag": "t", "page_pdf": "1",
                                      "page_printed": "1", "section": "1",
                                      "quantity": "q", "unit": "u", "published": "1",
                                      "expected": "2", "verdict": "agrees",
                                      "adjudication": ""}]),
    ("L5-5", "no reasoning", [{"module": "M1", "tag": "t", "page_pdf": "1",
                               "page_printed": "1", "section": "1", "quantity": "q",
                               "unit": "u", "published": "1", "expected": "2",
                               "verdict": "disputed", "adjudication": ""}]),
    ("L5-5", "dangling key", [{"module": "M1", "tag": "t", "page_pdf": "1",
                               "page_printed": "1", "section": "1", "quantity": "q",
                               "unit": "u", "published": "1", "expected": "2",
                               "verdict": "disputed", "adjudication": "Z-9"}]),
    # The retrieved form is policed exactly as hard as the paginated one.
    # It was added so a queried database need not invent a page number; that
    # is a reason to check it, not a reason to trust it.
    ("L5-2", "no location of any kind",
     [{"module": "M1", "tag": "t", "quantity": "q", "unit": "u",
       "published": "1", "expected": "1", "verdict": "agrees",
       "adjudication": ""}]),
    ("L5-2", "half a retrieved location",
     [{"module": "M1", "tag": "t", "url": "", "retrieved": "2026-08-31",
       "query": "argon 166 K", "quantity": "q", "unit": "u", "published": "1",
       "expected": "1", "verdict": "agrees", "adjudication": ""}]),
    ("L5-2", "a retrieval with no date",
     [{"module": "M1", "tag": "t", "url": "https://webbook.nist.gov/",
       "retrieved": "31/08/2026", "query": "argon 166 K", "quantity": "q",
       "unit": "u", "published": "1", "expected": "1", "verdict": "agrees",
       "adjudication": ""}]),
    ("L5-2", "a url that is not one",
     [{"module": "M1", "tag": "t", "url": "webbook.nist.gov",
       "retrieved": "2026-08-31", "query": "argon 166 K", "quantity": "q",
       "unit": "u", "published": "1", "expected": "1", "verdict": "agrees",
       "adjudication": ""}]),
    ("L5-2", "two kinds of location at once",
     [{"module": "M1", "tag": "t", "page_pdf": "1", "page_printed": "1",
       "section": "1", "url": "https://webbook.nist.gov/",
       "retrieved": "2026-08-31", "query": "argon", "quantity": "q",
       "unit": "u", "published": "1", "expected": "1", "verdict": "agrees",
       "adjudication": ""}]),
]


def self_test() -> int:
    """Hand the gate six known-bad fixtures and one good one."""
    source = "A-1 is adjudicated here."
    ok = True
    for rule, why, rows in BAD:
        faults = check(rows, source, "self-test")
        caught = any(rule in fault for fault in faults)
        print(f"  {'PASS' if caught else 'FAIL'}  {rule}  rejects {why}")
        ok &= caught

    good = {
        "paginated": [{"module": "M1", "tag": "t", "page_pdf": "1",
                       "page_printed": "1-2", "section": "1.1", "quantity": "q",
                       "unit": "u", "published": "1", "expected": "1",
                       "verdict": "agrees", "adjudication": ""}],
        "retrieved": [{"module": "M1", "tag": "t",
                       "url": "https://webbook.nist.gov/chemistry/fluid/",
                       "retrieved": "2026-08-31", "query": "argon, 166 K, 1 MPa",
                       "quantity": "q", "unit": "u", "published": "1",
                       "expected": "1", "verdict": "agrees", "adjudication": ""}],
    }
    for form, rows_ in good.items():
        quiet = not check(rows_, source, "self-test")
        print(f"  {'PASS' if quiet else 'FAIL'}  ----  accepts a well-formed "
              f"{form} row")
        ok &= quiet

    print("\n自检通过——闸门确实在工作" if ok else "\n自检失败——闸门不会报警")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        print("check_layer5.py 自检")
        return self_test()

    faults, total = gather(args.root)
    if faults:
        print(f"转录层裁定纪律：{len(faults)} 项不合规")
        for fault in faults:
            print(f"  {fault}")
        return 1
    if total < 0:
        print("尚不适用：layer5-secondsource 里还没有 fixture —— "
              "层 5 是唯一独立于主教材的一层，它现在是空的，"
              "而这件事记在立项书里，不是这道闸门要报的错")
        return 2
    print(f"转录层裁定纪律 ✓  {total} 行，每一行都有页码、裁定与出处"
          f"（层 1 印刷表 + 层 5 第二源）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

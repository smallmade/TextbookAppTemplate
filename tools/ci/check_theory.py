#!/usr/bin/env python3
"""Gate: every shipping module has theory behind it, and the theory names real code.

The theory manual is the most public document this project produces and the only
one that argues the results are trustworthy.  A module that reaches the manual
with no derivation, no assumptions and no stated limits does the opposite of
what the manual is for -- it presents a formula with the *appearance* of having
been justified.

Two checks, and the second is the one worth having:

  T-1  every core module in the canon has an entry, and every entry has every
       field.  Adding a module to the canon without writing its theory is then
       a failed build rather than a silent gap in a public document.

  T-2  every function named in an entry's `implements` actually exists in the
       package.  This is what keeps the prose anchored: rename a kernel function
       and the entry describing it fails here, instead of quietly going on to
       describe something that is no longer there.

T-2 exists because this project has already published a claim that was not true
of the code -- `docs/module-inventory.md` asserted two shipped features that had
never been implemented, and nothing caught it because nothing was checking
prose against code.  A sentence no mechanism can verify will drift; the only
question is how long before anyone notices.

Run with --self-test to prove the gate is alive.
"""

from __future__ import annotations

import argparse
import ast
import sys
import tomllib
from pathlib import Path

REQUIRED = ("implements", "basis", "derivation", "math",
            "assumptions", "method", "limitations", "reading")

#: Prose fields that must actually say something.  A present-but-empty `basis`
#: satisfies "has every field" while defeating the point of asking for one.
PROSE = ("basis", "derivation", "method", "reading")

#: Lists that must be non-empty.  `math` and `implements` are deliberately not
#: here: a module can legitimately have no display equation worth setting, and
#: one -- the topology screen -- computes nothing a kernel function owns.
NONEMPTY = ("assumptions", "limitations")

MIN_WORDS = 120

GREEN, RED, YELLOW, BOLD, OFF = (
    "\033[32m", "\033[31m", "\033[33m", "\033[1m", "\033[0m")


def public_names(package: Path) -> set[str]:
    """Every def in the package, found by parsing rather than importing.

    Same reasoning as the port-coverage gate: a hand-kept list of what exists
    drifts from what exists.
    """
    names: set[str] = set()
    for source in package.rglob("*.py"):
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
                names.add(node.name)
    return names


def load_entries(directory: Path) -> tuple[dict, list[str]]:
    entries: dict[str, dict] = {}
    faults: list[str] = []
    for path in sorted(directory.glob("*.toml")):
        if path.name == "front.toml":
            continue                       # chapters, not modules
        try:
            loaded = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            faults.append(f"{path.name}: 解析失败 —— {exc}")
            continue
        for module_id, entry in loaded.items():
            if module_id in entries:
                faults.append(f"{path.name}: {module_id} 在别的文件里已经定义过")
            entries[module_id] = entry
    return entries, faults


def check(root: Path) -> int:
    import json

    canon = json.loads((root / "spec" / "specification.json")
                       .read_text(encoding="utf-8"))
    shipping = [m["id"] for m in canon["modules"] if m["tier"] == "core"]
    entries, faults = load_entries(root / "docs" / "theory")
    known = public_names(root / "src" / "structurekit")

    for module_id in shipping:
        entry = entries.get(module_id)
        if entry is None:
            faults.append(f"{module_id}: 正典里有这个出货模组，理论手册里没有它的条目")
            continue
        for field in REQUIRED:
            if field not in entry:
                faults.append(f"{module_id}: 缺字段 {field}")
        for field in PROSE:
            text = entry.get(field) or ""
            if not str(text).strip():
                faults.append(f"{module_id}: {field} 是空的——有这个键不等于写了内容")
        for field in NONEMPTY:
            if not (entry.get(field) or []):
                faults.append(f"{module_id}: {field} 是空清单")
        words = sum(len(str(entry.get(f) or "").split()) for f in PROSE)
        if words and words < MIN_WORDS:
            faults.append(f"{module_id}: 正文只有 {words} 个词，"
                          f"不足 {MIN_WORDS}——这不是一条理论条目，是一句话")
        for name in entry.get("implements") or []:
            if name not in known:
                faults.append(f"{module_id}: implements 指名的 {name!r} "
                              f"在 src/structurekit 里不存在")

    for module_id in entries:
        if module_id not in shipping:
            faults.append(f"{module_id}: 理论手册有这个条目，正典里没有这个出货模组")

    print()
    print(f"{BOLD}闸门 · 理论手册的覆盖与锚定{OFF}")
    if faults:
        print(f"  {RED}✗{OFF} {len(faults)} 项不合规：")
        for fault in faults[:40]:
            print(f"      {fault}")
        if len(faults) > 40:
            print(f"      …… 另有 {len(faults) - 40} 项")
        print()
        print(f"{RED}{BOLD}未通过。{OFF}\n")
        return 1

    total = sum(sum(len(str(e.get(f) or "").split()) for f in PROSE)
                for e in entries.values())
    print(f"  {GREEN}✓{OFF} {len(shipping)} 个出货模组各有完整条目，"
          f"共 {total:,} 词，implements 指名的函数逐一存在")
    print()
    print(f"{GREEN}{BOLD}理论手册闸门通过。{OFF}\n")
    return 0


def self_test(root: Path) -> int:
    """A gate that has never been shown a fault is not evidence."""
    import json
    import tempfile

    canon = json.loads((root / "spec" / "specification.json")
                       .read_text(encoding="utf-8"))
    first = next(m["id"] for m in canon["modules"] if m["tier"] == "core")
    good = {f: ("x " * (MIN_WORDS // 4 + 5) if f in PROSE else ["a"])
            for f in REQUIRED}
    good["implements"] = []

    cases = [
        ("完整条目", good, True),
        ("缺一个字段", {k: v for k, v in good.items() if k != "method"}, False),
        ("字段在但内容是空的", {**good, "basis": "   "}, False),
        ("正文太短", {**good, "basis": "one", "derivation": "two",
                      "method": "three", "reading": "four"}, False),
        ("implements 指名不存在的函数",
         {**good, "implements": ["definitely_not_a_real_function"]}, False),
        ("清单是空的", {**good, "assumptions": []}, False),
    ]

    ok = True
    for label, entry, want_pass in cases:
        with tempfile.TemporaryDirectory() as tmp:
            probe = Path(tmp)
            (probe / "spec").mkdir()
            (probe / "docs" / "theory").mkdir(parents=True)
            (probe / "src" / "structurekit").mkdir(parents=True)
            (probe / "src" / "structurekit" / "k.py").write_text(
                "def only_real_function():\n    pass\n", encoding="utf-8")
            (probe / "spec" / "specification.json").write_text(json.dumps(
                {"modules": [{"id": first, "tier": "core"}]}), encoding="utf-8")
            body = [f"[{first}]"]
            for key, value in entry.items():
                if isinstance(value, list):
                    body.append(f"{key} = {json.dumps(value)}")
                else:
                    body.append(f"{key} = {json.dumps(value)}")
            (probe / "docs" / "theory" / "probe.toml").write_text(
                "\n".join(body) + "\n", encoding="utf-8")

            import io
            import contextlib
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = check(probe)
            passed = code == 0
            good_case = passed == want_pass
            ok &= good_case
            print(f"  {'PASS' if good_case else 'FAIL'}  {label}"
                  f"（{'通过' if passed else '未通过'}）")

    print("\n自检通过——闸门确实分得出完整条目与残缺条目"
          if ok else "\n自检失败")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test(args.root.resolve())
    return check(args.root.resolve())


if __name__ == "__main__":
    sys.exit(main())

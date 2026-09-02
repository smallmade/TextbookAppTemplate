#!/usr/bin/env python3
"""Gate 07 / M6 —— 两册手册与站点全文零教材标识，且公有领域来源具名。

规范 v5.0 §5.10「零教材痕迹」：两册、商店文案、站点、截图、审核说明、
`NSHumanReadableCopyright`——**任何面向用户的材料不得出现任何教材信息**。
负责人给的理由不是法律，是产品：会让用户误解为**还需要购买教材**。

`check_ship_isolation.py` 守的是出货正典这一个文件。这道守的是另一批出货面：
两册手册的 HTML、站点的每一页。两者用**同一份禁用词**，而且都从开发正典的
`sources[]` 派生——加一本教材进正典，两道闸门当天开始守它。手写的清单会
静默过期，而一份过期的隔离闸门报的是「通过」。

三类判据：

  **① 作者姓氏与完整书名**（≥4 字母的姓氏；≥12 字符的书名整串比对）。
  只取受版权来源的。公有领域来源的作者名是资产，不是风险。

  **② 结构性引用**：`Eq. 5.12` / `Sec. 3` / `Ch. 7` / `Table A-4` /
  `Example 5.3` / `Problem 9-2` / `§4` / `10th ed`。这些指向一本书，
  不管哪一本。**指向公有领域来源的除外**——`AFFDL-TR-69-42 Sec. A1` 是
  允许的，而且规范说具名它增强可信度。

  **③ 公有领域来源必须具名**（找不到任何一个时给警告，不判红）。
  「对照公有领域权威数据验证」是五条护城河里的「可验证」那一条，而它只有
  在**具名**时才起作用。这一条是警告不是失败，因为它是产品判断，不是缺陷。

    python tools/ci/check_manual_isolation.py [--root .] [--self-test]

退出码：0 通过 · 1 未通过 · 2 本阶段尚不适用。
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci_config import checked, load as load_config          # noqa: E402

TAG = re.compile(r"<[^>]+>")

#: 结构性引用。与 check_ship_isolation.py 同一张表——两道闸门守同一件事，
#: 两份表会漂。
STRUCTURAL: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bEq\.\s*\d", re.I), "式号"),
    (re.compile(r"\bsec\.\s*\d", re.I), "节号"),
    (re.compile(r"\bch\.\s*\d", re.I), "章号"),
    (re.compile(r"\bchapters?\s+\d", re.I), "章号"),
    (re.compile(r"\bTable\s+[A-Z]?-?\d"), "表号"),
    (re.compile(r"\bExample\s+\d", re.I), "例题号"),
    (re.compile(r"\bProblem\s+\d", re.I), "习题号"),
    (re.compile(r"§\s*\d"), "节号"),
    (re.compile(r"\b\d+(?:st|nd|rd|th)\s+ed\b", re.I), "版次"),
]


def plain(raw: str) -> str:
    return html.unescape(TAG.sub(" ", raw))


def _ambiguous_titles(spec: dict) -> set[str]:
    """同一个书名挂在两个以上不同作者名下 —— 那是**学科名**，不是书名。

    实测：MechanicsOne 的 primary-a（Hibbeler）、primary-b（Gere & Goodno）、
    primary-c（Gere & Timoshenko）三本书的 title 都是
    `Mechanics of Materials`——因为那是这门课的名字。站点首页那句
    「mechanics of materials, worked interactively」被判成三次书名泄漏，
    而它一本书也没指。

    判据是可派生的，不是一份手写的学科名清单：**一个书名要能识别一本书，
    它得对应唯一一个作者。** 对应两个以上，它携带的识别信息就是零。
    同一本书的两个版次（同名同作者）不受影响，仍然算标识。
    """
    by_title: dict[str, set[str]] = {}
    for source in spec.get("sources", []):
        title = (source.get("title") or "").strip().lower()
        if not title:
            continue
        by_title.setdefault(title, set()).add(
            (source.get("author") or "").strip().lower())
    return {title for title, authors in by_title.items() if len(authors) > 1}


def copyrighted_terms(spec: dict) -> list[tuple[re.Pattern, str]]:
    """受版权来源的作者姓氏与完整书名，从正典派生。"""
    out: list[tuple[re.Pattern, str]] = []
    ambiguous = _ambiguous_titles(spec)
    for source in spec.get("sources", []):
        if source.get("licence") != "copyrighted":
            continue
        key = source.get("key", "?")
        for name in re.split(r"[,&]| and ", source.get("author", "")):
            words = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]+", name)
                     if len(w) >= 4]
            if words:
                out.append((re.compile(rf"\b{re.escape(words[-1])}\b", re.I),
                            f"{key} 的作者姓氏"))
        title = (source.get("title") or "").strip()
        if len(title) >= 12 and title.lower() not in ambiguous:
            out.append((re.compile(re.escape(title), re.I), f"{key} 的书名"))
    return out


def public_domain_names(spec: dict) -> list[str]:
    """可以具名、而且应该具名的公有领域来源。

    **`key` 也算**，而且它是实践中最常出现的那一种：理论手册的验证节写的
    是 `affdl-sam Ch. 3` / `nasa-asm Sec. A1`——用正典里的 key 指认来源。
    不把 key 收进来，这些合法的具名引用会被当成结构性引用报红（实测 2 处），
    而它们正是规范鼓励的写法。
    """
    names = []
    for source in spec.get("sources", []):
        if source.get("licence") != "public-domain":
            continue
        for field in ("key", "edition", "title", "author"):
            value = (source.get(field) or "").strip()
            if value:
                names.append(value)
    return names


def cites_public_domain(text: str, allowed: list[str]) -> bool:
    """这段文字里点名的是一份公有领域来源吗？"""
    lowered = text.lower()
    return any(name.lower() in lowered for name in allowed
               if len(name) >= 6)


def scan(text: str, terms, allowed: list[str], where: str) -> list[str]:
    """逐行扫，行号照报——手册几万字，光说「命中」找不到地方。"""
    hits: list[str] = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        for pattern, why in terms:
            match = pattern.search(line)
            if match:
                hits.append(f"{where}:{number}  {match.group(0)!r}  {why}")
        for pattern, why in STRUCTURAL:
            match = pattern.search(line)
            if not match:
                continue
            if cites_public_domain(line, allowed):
                continue        # 指向公有领域来源的结构性引用是允许的
            hits.append(f"{where}:{number}  {match.group(0)!r}  {why}")
    return hits


# ──────────────────────────────── 自检 ────────────────────────────────

SPEC = {"sources": [
    {"key": "primary-a", "author": "R. C. Hibbeler",
     "title": "Mechanics of Materials", "licence": "copyrighted"},
    {"key": "affdl-sam", "author": "Air Force Flight Dynamics Laboratory",
     "title": "Stress Analysis Manual", "edition": "AFFDL-TR-69-42",
     "licence": "public-domain"},
]}


def self_test() -> int:
    ok = True
    terms = copyrighted_terms(SPEC)
    allowed = public_domain_names(SPEC)

    bad = [
        ("作者姓氏", "The derivation follows Hibbeler closely."),
        ("完整书名", "See Mechanics of Materials for the general case."),
        ("式号", "as given in Eq. 5.12 of the course text"),
        ("章号", "Ch. 7 covers the unsymmetric case"),
        ("表号", "Table A-4 lists the allowable stresses"),
        ("例题号", "Example 5.3 works this out"),
        ("习题号", "Problem 9-2 asks for the same quantity"),
        ("版次", "the 10th ed uses a different sign convention"),
    ]
    for label, line in bad:
        caught = bool(scan(line, terms, allowed, "m.html"))
        ok &= caught
        print(f"  {'PASS' if caught else 'FAIL'}  拒绝  {label}")

    good = [
        ("指向公有领域来源的节号", "AFFDL-TR-69-42 Sec. A1 gives the curve"),
        ("公有领域来源的作者名", "Air Force Flight Dynamics Laboratory data"),
        ("学科日常词汇", "The second law forbids this outcome."),
        ("量纲与数字", "sigma = 250 MPa at 20 degrees"),
        ("普通的表格说明", "The table below lists the section properties."),
    ]
    for label, line in good:
        found = scan(line, terms, allowed, "m.html")
        quiet = not found
        ok &= quiet
        print(f"  {'PASS' if quiet else 'FAIL'}  放行  {label}"
              + ("" if quiet else f"   ← 误报：{found}"))

    named = cites_public_domain("verified against AFFDL-TR-69-42", allowed)
    ok &= named
    print(f"  {'PASS' if named else 'FAIL'}  识别  公有领域来源已具名")

    anonymous = not cites_public_domain(
        "verified against published data", allowed)
    ok &= anonymous
    print(f"  {'PASS' if anonymous else 'FAIL'}  识别  「公开数据」不算具名")

    # 实测误报 ①：理论手册用正典的 key 指认公有领域来源
    # （`affdl-sam Ch. 3`）。key 必须算「已具名」，否则这些合法引用被判红。
    quiet = not scan("nasa-asm Sec. A1; affdl-sam Ch. 3", terms, allowed,
                     "t.html")
    ok &= quiet
    print(f"  {'PASS' if quiet else 'FAIL'}  放行  用正典 key 指认公有领域来源")

    # 实测误报 ②：三本教材共用书名 `Mechanics of Materials`——那是学科名。
    ambiguous_spec = {"sources": [
        {"key": "a", "author": "R. C. Hibbeler",
         "title": "Mechanics of Materials", "licence": "copyrighted"},
        {"key": "b", "author": "J. M. Gere",
         "title": "Mechanics of Materials", "licence": "copyrighted"},
    ]}
    shared = copyrighted_terms(ambiguous_spec)
    quiet = not any(pattern.search("mechanics of materials, worked "
                                   "interactively")
                    for pattern, _ in shared)
    ok &= quiet
    print(f"  {'PASS' if quiet else 'FAIL'}  放行  两个作者共用的书名 = 学科名")

    # ……但同一本书的两个版次（同名【同】作者）仍然算标识。
    editions_spec = {"sources": [
        {"key": "a", "author": "R. C. Hibbeler", "edition": "10th",
         "title": "Statics and Mechanics", "licence": "copyrighted"},
        {"key": "a2", "author": "R. C. Hibbeler", "edition": "11th",
         "title": "Statics and Mechanics", "licence": "copyrighted"},
    ]}
    caught = any(pattern.search("see Statics and Mechanics for details")
                 for pattern, _ in copyrighted_terms(editions_spec))
    ok &= caught
    print(f"  {'PASS' if caught else 'FAIL'}  拒绝  同名【同】作者的两个版次"
          f"仍然是标识")

    print("\n自检通过——闸门既不漏报也不乱叫" if ok else "\n自检失败")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        print("check_manual_isolation.py 自检")
        return self_test()

    root = args.root.resolve()
    cfg = load_config(root)
    spec_path = cfg.path("canon") or (root / "spec" / "specification.json")
    if not spec_path.is_file():
        print("尚不适用：还没有开发正典——禁用词从它派生", file=sys.stderr)
        return 2
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    terms = copyrighted_terms(spec)
    allowed = public_domain_names(spec)

    targets: list[Path] = [p for p in cfg.paths("manual_paths") if p.is_file()]
    site_dir = cfg.path("site_dir")
    if site_dir and site_dir.is_dir():
        targets += [p for p in sorted(site_dir.rglob("*.html"))
                    if p not in targets]
    targets = sorted(set(targets))

    if not targets:
        print("尚不适用：两册手册与站点都还没有（阶段 07 之前正常）",
              file=sys.stderr)
        return 2
    if not terms:
        print("尚不适用：正典里没有受版权来源，派生不出禁用词。"
              "（这本身可能是对的——也可能是 sources[] 没写全。）",
              file=sys.stderr)
        return 2

    hits: list[str] = []
    named_anywhere = False
    for path in targets:
        text = plain(path.read_text(encoding="utf-8", errors="ignore"))
        hits += scan(text, terms, allowed, str(path.relative_to(root)))
        named_anywhere |= cites_public_domain(text, allowed)

    print(checked(len(targets), "个出货面（手册页 + 站点页）",
                  f"{len(terms)} 条派生禁用词 + {len(STRUCTURAL)} 条结构模式"))
    if not targets:
        print("✗ 一个出货面都没扫到——这不是通过，这是没检查。")
        return 1

    if hits:
        print(f"✗ {len(hits)} 处教材标识：")
        for line in hits[:30]:
            print(f"    {line}")
        if len(hits) > 30:
            print(f"    …… 另 {len(hits) - 30} 处")
        print("  规范 v5.0 §5.10：任何面向用户的材料不得出现任何教材信息。")
        print("  理由不是法律，是产品——会让用户以为还需要购买教材。")
        return 1
    print(f"✓ {len(targets)} 个出货面零教材标识")

    if not named_anywhere:
        print("⚠ 两册与站点里找不到任何公有领域来源的具名。")
        print("  「对照公有领域权威数据验证」是五条护城河里的『可验证』，"
              "而它只有在具名时才起作用（NACA / NASA / NIST / IAPWS 具名"
              "零法律风险且增强可信度）。")
        print("  这一条是警告，不是失败——它是产品判断。")
    else:
        print("✓ 公有领域来源在出货面上有具名")
    return 0


if __name__ == "__main__":
    sys.exit(main())

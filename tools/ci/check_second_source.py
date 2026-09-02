#!/usr/bin/env python3
"""闸门 —— 正典的 `second_source` 声明与层 5 实际建成的 fixture 对得上。

这道闸门要防的是一个**已经发生过三次**的错误族：
**一个读起来像「已验证」的声明，实际上只是「有来源可用」。**

  * 判例集第 43 条：`coverage-audit-posable.csv` 照正典的声明列输入，当作
    界面的实现用，断言「35/35 都有画面收留」——实测两个模块根本没有入口。
  * 判例集第 50 条：正典的 `printed_table` 按学科常识写下，没有去看；
    看过之后 M02/M03 两条都得改回 false。
  * 本条（2026-08-31 对照蓝图时发现）：正典为 **42** 个 module 具名了
    second_source，实际建成层 5 fixture 的只有 **18** 个；而 M05、M17
    明明已经有 fixture，正典却仍写着 null。

`second_source` 这个字段的真实含义是「**找得到一份可用的来源**」，
不是「**已经比对过了**」。两者差得很远，而把前者写在一个叫 second_source
的字段里，半年后一定会被读成后者。

所以这道闸门查两个方向，且**只有一个方向是错误**：

  S-1  **正典说 null，实际却有 fixture** —— 这是真的错（漏更新）。
       层 5 建好了却没回填正典，下一个人读正典会以为这个模块没有第二源。
  S-2  **正典具名，实际没有 fixture** —— 这**不是**错，是正常的待办状态。
       但它必须被【报出来】，而且报的时候两个数要分开写，
       不许让「42」这个数字单独出现在任何地方被当成覆盖率。

不把 S-2 判成失败是刻意的：一个在正常状态下就红的闸门，两天之内会被关掉。
它要做的是让那个差距**一直可见**，而不是让它变成一次失败。

    python tools/ci/check_second_source.py [--root .] [--self-test]

退出码：0 通过 · 1 有 S-1 违规 · 2 尚不适用（没有正典或没有层 5 目录）。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

LAYER = "layer5-secondsource"


def fixtured_modules(root: Path) -> set[str] | None:
    """哪些 module 真的有层 5 的行。目录不存在时返回 None（尚不适用）。"""
    roots = (root / "tests" / "data", root / "python" / "tests" / "data")
    data = next((p for p in roots if p.is_dir()), None)
    if data is None:
        return None
    directory = data / LAYER
    if not directory.is_dir():
        return None
    found: set[str] = set()
    for fixture in sorted(directory.glob("*.csv")):
        body = [line for line in fixture.read_text(encoding="utf-8").splitlines()
                if not line.lstrip().startswith("#")]
        for row in csv.DictReader(body):
            module = (row.get("module") or "").strip()
            if module:
                found.add(module)
    return found


def declared_sources(spec_path: Path) -> dict[str, str]:
    """module id -> second_source 声明（空字符串表示 null / 未声明）。"""
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    return {m["id"]: (m.get("second_source") or "").strip()
            for m in spec.get("modules", [])}


def audit(declared: dict[str, str], fixtured: set[str]) -> tuple[list[str], list[str]]:
    """返回 (S-1 违规, S-2 仅具名未建成)。"""
    stale = sorted(m for m in fixtured if not declared.get(m, ""))
    named_only = sorted(m for m, source in declared.items()
                        if source and m not in fixtured)
    return stale, named_only


SELF_TEST = [
    # M02 具名却没有 fixture，所以它【应该】出现在 named_only 里。
    # 这个样本第一次写错了期望值（漏了 M02），闸门把它顶了回来——
    # 自检样本自己写错时会失败，正是它该有的样子。
    ("S-1 正典说 null 但有 fixture",
     {"M01": "", "M02": "somewhere"}, {"M01"}, ["M01"], ["M02"]),
    ("S-1 多个模块同时漏更新",
     {"M01": "", "M02": ""}, {"M01", "M02"}, ["M01", "M02"], []),
    ("放行：声明与 fixture 一致",
     {"M01": "a source", "M02": ""}, {"M01"}, [], []),
    ("S-2 具名但未建成——报告，不失败",
     {"M01": "a source"}, set(), [], ["M01"]),
    ("fixture 里出现正典没有的 module 也算 S-1",
     {"M01": "a source"}, {"M01", "M99"}, ["M99"], []),
]


def self_test() -> int:
    ok = True
    for label, declared, fixtured, want_stale, want_named in SELF_TEST:
        stale, named = audit(declared, fixtured)
        good = (stale == want_stale and named == want_named)
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  {label}")
        if not good:
            print(f"        got stale={stale} named_only={named}, "
                  f"want stale={want_stale} named_only={want_named}")
    print("\n自检通过——闸门确实在工作" if ok else "\n自检失败——闸门不会报警")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--spec", default=None, type=Path)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        print("check_second_source.py 自检")
        return self_test()

    root = args.root.resolve()
    spec_path = args.spec or (root / "spec" / "specification.json")
    if not spec_path.is_file():
        print(f"尚不适用：没有 {spec_path}", file=sys.stderr)
        return 2
    fixtured = fixtured_modules(root)
    if fixtured is None:
        print(f"尚不适用：没有 {LAYER}/", file=sys.stderr)
        return 2

    declared = declared_sources(spec_path)
    stale, named_only = audit(declared, fixtured)

    # S-2 先报，因为它是常态，而这道闸门的一半价值就是让这个差距一直可见。
    print(f"层 5 已建成 fixture：{len(fixtured)} 个 module")
    print(f"正典已具名 second_source：{sum(1 for v in declared.values() if v)} 个 module")
    if named_only:
        print(f"  其中 {len(named_only)} 个只是【具名】、尚未建成 fixture —— "
              f"这是待办，不是错，但不要把「已具名」的数字当成覆盖率：")
        print(f"    {' '.join(named_only)}")

    if stale:
        print(f"\n✗ S-1：{len(stale)} 个 module 有层 5 fixture，"
              f"正典却没有声明 second_source：")
        for module in stale:
            print(f"    {module}")
        print("  层 5 建好了要回填正典。否则下一个人读正典，会以为这个模块"
              "没有第二源——而它其实有。")
        return 1

    print("\n✓ 凡有层 5 fixture 的 module，正典都声明了 second_source")
    return 0


if __name__ == "__main__":
    sys.exit(main())

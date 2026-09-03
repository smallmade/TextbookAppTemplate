#!/usr/bin/env python3
"""[M-C1] 把一次设备矩阵采集的登记表变成可评审的东西。

    python3 tools/shots/matrix_report.py <采集目录> [--root .] [--table]
    python3 tools/shots/matrix_report.py --self-test

产出两样：

  `manifest.json` —— 每一格的机器记录。**记的是实际拿到的尺寸**，不是请求
  的尺寸。窗口服务器会把超过可用区的请求钳住，而一份记着「请求 2400×1300」
  的清单，读起来像这一档跑过了。两个数都记，差异单独列一节。

  `--table` —— 评分表骨架（Markdown），贴进 docs/device-matrix.md 由人填。
  骨架里每一格预填的是 `?`，不是 `3`。**预填满分的表，人会照单签收。**

退出码：0 有产出 · 1 登记表为空或不存在（零格不是通过）。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

FIELDS = ("status", "device", "screen", "appearance", "want_w", "want_h",
          "got_w", "got_h", "px_w", "px_h", "file", "note")

#: 规范 v5.0 §7.3 的检查项。评分表的列就是这几条，顺序固定——
#: 每次换一套检查项，两次评分就不可比了。
CRITERIA = ("截断", "重叠", "溢出", "空旷", "拥挤", "首屏可见结果",
            "字号", "触控 44pt", "深色对比")


def read_manifest(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if i == 0 or not line.strip():
            continue
        parts = line.split("\t")
        parts += [""] * (len(FIELDS) - len(parts))
        rows.append(dict(zip(FIELDS, parts)))
    return rows


def summarise(rows: list[dict]) -> dict:
    by_status = Counter(r["status"] for r in rows)
    cells = {(r["device"], r["screen"], r["appearance"])
             for r in rows if r["status"] == "ok"}
    devices = defaultdict(Counter)
    for r in rows:
        devices[r["device"]][r["status"]] += 1
    # 宽和高都要比。只比宽的那一版放过了 2500×1400 → 2500×1030 这一档，
    # 而这台机器上放不下的两档正好都是【高】不够——一个只比宽的检查在
    # 这里恰好一格都抓不到，还印「全部对得上」。
    mismatched = [r for r in rows
                  if (r["got_w"] and r["want_w"] and r["got_w"] != r["want_w"])
                  or (r["got_h"] and r["want_h"] and r["got_h"] != r["want_h"])]
    return {
        "rows": len(rows),
        "by_status": dict(by_status),
        "matrix_cells": len(cells),
        "per_device": {k: dict(v) for k, v in sorted(devices.items())},
        "size_clamped": [
            {"device": r["device"], "want": f'{r["want_w"]}x{r["want_h"]}',
             "got": f'{r["got_w"]}x{r["got_h"]}', "note": r["note"]}
            for r in mismatched],
    }


def table(rows: list[dict]) -> str:
    """评分表骨架：一档一节，一屏一行，检查项一列，全部预填 `?`。"""
    ok = [r for r in rows if r["status"] == "ok"]
    if not ok:
        return "（本次没有任何入矩阵的格，评分表为空。零格不是通过。）\n"
    out: list[str] = []
    devices = sorted({r["device"] for r in ok})
    for dev in devices:
        mine = [r for r in ok if r["device"] == dev]
        got = mine[0]
        out.append(f"\n#### {dev}　实测 {got['got_w']}×{got['got_h']}pt"
                   f"（{got['px_w']}×{got['px_h']}px）\n")
        out.append("| 画面 | 外观 | 分 | " + " | ".join(CRITERIA) + " | 说明 |")
        out.append("|---|---|---|" + "---|" * len(CRITERIA) + "---|")
        for r in sorted(mine, key=lambda x: (x["screen"], x["appearance"])):
            out.append(f"| {r['screen']} | {r['appearance']} | ? | "
                       + " | ".join("?" for _ in CRITERIA) + " |  |")
    return "\n".join(out) + "\n"


def self_test() -> int:
    ok = True
    rows = [
        {"status": "ok", "device": "mac-default-window", "screen": "columns",
         "appearance": "light", "want_w": "1180", "want_h": "800",
         "got_w": "1180", "got_h": "800", "px_w": "2360", "px_h": "1600",
         "file": "x.png", "note": ""},
        {"status": "unreachable", "device": "mac-external-4k5k",
         "screen": "columns", "appearance": "light", "want_w": "2500",
         "want_h": "1400", "got_w": "2500", "got_h": "1030", "px_w": "",
         "px_h": "", "file": "", "note": "本机屏幕放不下"},
    ]
    s = summarise(rows)

    good = s["matrix_cells"] == 1
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  只把 ok 的那一行算进矩阵格")

    good = len(s["size_clamped"]) == 1 and \
        s["size_clamped"][0]["got"] == "2500x1030"
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  钳过的档记的是【实际拿到的】"
          f"尺寸，不是请求的")

    good = "?" in table(rows) and "| 3 |" not in table(rows)
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  骨架预填 `?` 而不是满分")

    good = table([]).startswith("（本次没有任何入矩阵的格")
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  零格时说「零格不是通过」")

    print("\n自检通过" if ok else "\n自检失败")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out_dir", nargs="?", type=Path)
    ap.add_argument("--table", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        print("matrix_report.py 自检")
        return self_test()
    if args.out_dir is None:
        ap.error("要给采集目录")

    rows = read_manifest(args.out_dir / "_manifest.tsv")
    if not rows:
        print(f"✗ {args.out_dir}/_manifest.tsv 是空的或不存在——"
              f"一格都没采到不是通过。", file=sys.stderr)
        return 1

    summary = summarise(rows)
    (args.out_dir / "manifest.json").write_text(
        json.dumps({"summary": summary, "cells": rows},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    if args.table:
        print(table(rows))
        return 0

    print(f"CHECKED n={summary['rows']} 行登记 · "
          f"入矩阵 {summary['matrix_cells']} 格")
    for status, n in sorted(summary["by_status"].items()):
        print(f"    {status:<14} {n}")
    if summary["size_clamped"]:
        print("  本机屏幕放不下的档（记的是实际拿到的尺寸）：")
        for c in summary["size_clamped"]:
            print(f"    {c['device']:<22} 要 {c['want']}  得 {c['got']}"
                  f"  {c['note']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

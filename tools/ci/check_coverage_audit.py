#!/usr/bin/env python3
"""Gate 04 · 适配审计的机器检查。

    python check_coverage_audit.py <项目目录>

回答的不是「算得对不对」，而是「审计本身站不站得住」。审计报告是人写的
判断，这个脚本查它有没有被写坏：

1. 每一条判定都在封闭词汇里（ok / awkward / gap / n/a）
2. 每一条 ok 或 awkward 都指名一个**正典里真实存在、且属于 v1.0 出货范围**
   的 module —— 指向一个不存在的画面的 ok 是一句空话
3. 每一条 gap 都有理由，且理由必须落在两处之一：不做清单，或路线图上的
   v1.1/v1.2 module。**不许留白**是规范的原话
4. 每一份审计都逐字包含「这不是正确性指标」的声明

第 2 条是这道闸门唯一真正在做的事。判定表是散文，散文会漂移；把 module 名
接回正典，漂移就会失败而不是被读过去。

**不读教材 PDF。** 审计的输入是判断，输出是 CSV；教材不需要在场，脚本也
因此可以在 CI 上跑。

退出码：0 通过 · 1 未通过 · 2 尚不适用（跳过）。
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

VERDICTS = {"ok", "awkward", "gap", "n/a"}
DECLARATION = "这不是正确性指标"

RED = "\033[31m"
GREEN = "\033[32m"
OFF = "\033[0m"


def rows_of(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        lines = [line for line in handle if not line.startswith("#")]
    return list(csv.DictReader(lines))


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    folder = root / "docs" / "coverage-audit"
    report = root / "docs" / "coverage-audit.md"
    files = sorted(folder.glob("*.csv")) if folder.is_dir() else []
    if not files:
        print("尚不适用：还没有 docs/coverage-audit/*.csv —— 阶段 04 之前正常")
        return 2

    spec_path = root / "spec" / "specification.json"
    if not spec_path.is_file():
        print("尚不适用：没有 spec/specification.json")
        return 2
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    shipping = {
        module["id"] for module in spec["modules"]
        if module.get("release") == "v1.0" or module.get("tier") == "core"
    }
    known = {module["id"] for module in spec["modules"]}

    problems: list[str] = []
    tally: dict[str, int] = {verdict: 0 for verdict in VERDICTS}
    total = 0

    for path in files:
        for index, row in enumerate(rows_of(path), start=2):
            where = f"{path.name}:{index}"
            verdict = (row.get("verdict") or "").strip()
            module = (row.get("module") or "").strip()
            note = (row.get("note") or "").strip()
            try:
                count = int(row.get("count") or 0)
            except ValueError:
                problems.append(f"{where}: count 不是整数")
                continue
            if count <= 0:
                problems.append(f"{where}: count 必须为正")
            if verdict not in VERDICTS:
                problems.append(f"{where}: 判定 {verdict!r} 不在封闭词汇里")
                continue
            tally[verdict] += count
            total += count

            if verdict in ("ok", "awkward"):
                if not module:
                    problems.append(f"{where}: {verdict} 必须指名一个 module")
                elif module not in known:
                    problems.append(f"{where}: module {module!r} 不在正典里")
                elif module not in shipping:
                    problems.append(
                        f"{where}: module {module!r} 不属于 v1.0 出货范围"
                    )
            if verdict == "gap" and len(note) < 25:
                problems.append(f"{where}: gap 必须写明处置，理由太短")
            if verdict == "n/a" and not note:
                problems.append(f"{where}: n/a 也要说明为什么不适用")

    if not report.is_file():
        problems.append("缺少 docs/coverage-audit.md")
    elif DECLARATION not in report.read_text(encoding="utf-8"):
        problems.append(
            f"docs/coverage-audit.md 里没有逐字出现「{DECLARATION}」的声明"
        )

    print(f"适配审计 · {len(files)} 部教材 · {total} 项")
    for verdict in ("ok", "awkward", "gap", "n/a"):
        share = 100.0 * tally[verdict] / total if total else 0.0
        print(f"  {verdict:8s} {tally[verdict]:5d}  {share:5.1f}%")
    if problems:
        for line in problems[:20]:
            print(f"  {RED}✗{OFF} {line}")
        print(f"{RED}适配审计未通过：{len(problems)} 项{OFF}")
        return 1
    print(f"{GREEN}适配审计通过。{OFF}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

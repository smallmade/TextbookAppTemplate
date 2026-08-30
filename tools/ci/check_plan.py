#!/usr/bin/env python3
"""闸门 —— 施工书的进度台账，以及标成 done 的项是不是真的立得住。

它回答两个问题，**第二个才是重点**：

  1. 台账里每一项处于什么状态。
  2. 标成 `done` 的项，它的闸门**是不是真的存在、是不是真的被 runner 调用**。

第二问是这个脚本存在的理由。本项目的判例集第 42 条：
**一道存在但没人调用的闸门，比没有闸门更糟**——没有闸门时你至少知道自己
没检查；有一个没人调用的闸门时，源码、文档、台账都在暗示这件事已经查过了。

    python3 tools/ci/check_plan.py              # 报告 + 校验
    python3 tools/ci/check_plan.py --summary    # 只报告，永远退出 0
    python3 tools/ci/check_plan.py --self-test  # 交给它已知不合格的样本

退出码：0 通过 · 1 某个 done 项的闸门立不住 · 2 台账本身损坏。

──────────────────────────────────────────────────────────────
两个文件，故意分开
──────────────────────────────────────────────────────────────

    docs/PLAN-STATUS.tsv    台账本身，一行一项
    docs/PLAN-COUNTS.tsv    每个前缀应有多少项 + 总数

分开是**故意的摩擦**：增删一项必须同时改两处，否则报「台账损坏」。
手写的「哪些算数」清单每一次都漏掉东西——判例集第 10、13、36、43 条
全是同一个族。计数放在第二个文件里，是让「悄悄删掉一行」变成一件会失败
的事。
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

VALID = {"todo", "wip", "done", "dropped"}
RED, GREEN, YELLOW, DIM, BOLD, OFF = (
    "\033[31m", "\033[32m", "\033[33m", "\033[2m", "\033[1m", "\033[0m")


def read_tsv(path: Path) -> list[dict[str, str]]:
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines()
             if not ln.startswith("#")]
    return list(csv.DictReader(lines, delimiter="\t"))


def load_counts(path: Path) -> tuple[int, dict[str, int], list[str]]:
    if not path.is_file():
        return 0, {}, [f"{path.name} 不存在"]
    total, per = 0, {}
    for row in read_tsv(path):
        key, value = row["prefix"].strip(), row["count"].strip()
        if not key:
            continue
        try:
            number = int(value)
        except ValueError:
            return 0, {}, [f"{path.name}: {key} 的计数不是整数：{value!r}"]
        if key == "TOTAL":
            total = number
        else:
            per[key] = number
    return total, per, []


def validate(rows: list[dict[str, str]], total: int,
             per: dict[str, int]) -> list[str]:
    """台账自身是否完好。任何一条不满足即退出码 2。"""
    problems: list[str] = []
    if len(rows) != total:
        problems.append(f"台账有 {len(rows)} 项，PLAN-COUNTS.tsv 说应有 {total}")
    ids = [r["id"] for r in rows]
    duplicated = sorted({i for i in ids if ids.count(i) > 1})
    if duplicated:
        problems.append(f"重复的 id：{duplicated}")
    actual: dict[str, int] = {}
    for i in ids:
        actual[i.split("-", 1)[0]] = actual.get(i.split("-", 1)[0], 0) + 1
    for prefix, expected in sorted(per.items()):
        if actual.get(prefix, 0) != expected:
            problems.append(f"分组 {prefix} 有 {actual.get(prefix, 0)} 项，应有 {expected}")
    for prefix in sorted(set(actual) - set(per)):
        problems.append(f"分组 {prefix} 不在 PLAN-COUNTS.tsv 里")
    for row in rows:
        if row["status"] not in VALID:
            problems.append(f"{row['id']}：状态 {row['status']!r} 不在 "
                            f"{sorted(VALID)} 里")
        if not row.get("gate", "").strip():
            problems.append(f"{row['id']}：没有写闸门。**一条没有验收方式的条目"
                            f"不是条目，是愿望**")
    return problems


def runner_text(root: Path) -> str:
    """所有 runner 的正文，用来判断一个闸门是不是真的被调用。"""
    chunks = []
    for directory in (root / "tools" / "ci", root / "tools" / "build"):
        if directory.is_dir():
            for runner in sorted(directory.glob("run_*.sh")):
                chunks.append(runner.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


def audit_done(rows: list[dict[str, str]], root: Path) -> list[str]:
    """标成 done 的项，闸门必须存在**并且**被 runner 调用。"""
    called = runner_text(root)
    faults: list[str] = []
    for row in rows:
        if row["status"] != "done":
            continue
        script = row.get("gate_script", "").strip()
        if not script:
            faults.append(f"{row['id']}：标成 done，但 gate_script 是空的")
            continue
        if not (root / script).is_file():
            faults.append(f"{row['id']}：闸门脚本不存在：{script}")
            continue
        if Path(script).name not in called:
            faults.append(f"{row['id']}：闸门 {Path(script).name} "
                          f"没有被任何 run_*.sh 调用——"
                          f"存在但没人调用的闸门比没有闸门更糟")
    return faults


def report(rows: list[dict[str, str]]) -> None:
    order = {"done": 0, "wip": 1, "todo": 2, "dropped": 3}
    mark = {"done": f"{GREEN}✓{OFF}", "wip": f"{YELLOW}◐{OFF}",
            "todo": f"{DIM}·{OFF}", "dropped": f"{DIM}✗{OFF}"}
    phases: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        phases.setdefault(row["phase"], []).append(row)
    for phase, items in phases.items():
        tally = {k: sum(1 for i in items if i["status"] == k) for k in VALID}
        print(f"\n{BOLD}{phase}{OFF}  "
              f"{GREEN}{tally['done']} done{OFF} · "
              f"{tally['wip']} wip · {tally['todo']} todo"
              + (f" · {tally['dropped']} dropped" if tally["dropped"] else ""))
        for row in sorted(items, key=lambda r: (order[r["status"]], r["id"])):
            print(f"  {mark[row['status']]} {row['id']:<6} {row['title'][:62]}")


#: 已知不合格的台账，每一个都必须被拒。一道「没找到问题就算通过」的检查，
#: 必须有一个已知会失败的样本证明它真的在工作。
BAD = [
    ("少一行", [{"id": "X-01", "status": "done", "phase": "p", "kind": "k",
                 "title": "t", "site": "", "gate": "g", "gate_script": ""}], 1, {"X": 2}),
    ("重复 id", [{"id": "X-01", "status": "todo", "phase": "p", "kind": "k",
                  "title": "t", "site": "", "gate": "g", "gate_script": ""},
                 {"id": "X-01", "status": "todo", "phase": "p", "kind": "k",
                  "title": "t", "site": "", "gate": "g", "gate_script": ""}], 2, {"X": 2}),
    ("状态不在词汇里", [{"id": "X-01", "status": "almost", "phase": "p", "kind": "k",
                        "title": "t", "site": "", "gate": "g", "gate_script": ""}], 1, {"X": 1}),
    ("条目没有闸门", [{"id": "X-01", "status": "todo", "phase": "p", "kind": "k",
                      "title": "t", "site": "", "gate": "", "gate_script": ""}], 1, {"X": 1}),
    ("分组计数对不上", [{"id": "X-01", "status": "todo", "phase": "p", "kind": "k",
                        "title": "t", "site": "", "gate": "g", "gate_script": ""}], 1, {"X": 5}),
]


def self_test(root: Path) -> int:
    ok = True
    for label, rows, total, per in BAD:
        caught = bool(validate(rows, total, per))
        print(f"  {'PASS' if caught else 'FAIL'}  拒绝  {label}")
        ok &= caught

    good = [{"id": "X-01", "status": "todo", "phase": "p", "kind": "k",
             "title": "t", "site": "", "gate": "g", "gate_script": ""}]
    quiet = not validate(good, 1, {"X": 1})
    print(f"  {'PASS' if quiet else 'FAIL'}  放行  一份完好的台账")
    ok &= quiet

    # done 但闸门不存在 / 没人调用，必须被抓
    missing = [{"id": "G-99", "status": "done", "phase": "p", "kind": "k",
                "title": "t", "site": "", "gate": "g",
                "gate_script": "tools/ci/does_not_exist.py"}]
    caught = bool(audit_done(missing, root))
    print(f"  {'PASS' if caught else 'FAIL'}  拒绝  done 项的闸门脚本不存在")
    ok &= caught

    orphan = [{"id": "G-98", "status": "done", "phase": "p", "kind": "k",
               "title": "t", "site": "", "gate": "g",
               "gate_script": "tools/ci/render_source_page.py"}]
    caught = bool(audit_done(orphan, root))
    print(f"  {'PASS' if caught else 'FAIL'}  拒绝  done 项的闸门没被任何 runner 调用")
    ok &= caught

    print("\n自检通过——闸门确实在工作" if ok else "\n自检失败——闸门不会报警")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=None, type=Path)
    ap.add_argument("--summary", action="store_true", help="只报告，永远退出 0")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    root = (args.root or Path(__file__).resolve().parents[2]).resolve()
    if not (root / "docs" / "PLAN-STATUS.tsv").is_file():
        root = Path.cwd().resolve()

    if args.self_test:
        print("check_plan.py 自检")
        return self_test(root)

    ledger = root / "docs" / "PLAN-STATUS.tsv"
    if not ledger.is_file():
        print(f"尚不适用：没有 {ledger.relative_to(root)} —— 还没有施工书",
              file=sys.stderr)
        return 2

    rows = read_tsv(ledger)
    total, per, count_problems = load_counts(root / "docs" / "PLAN-COUNTS.tsv")
    problems = count_problems + validate(rows, total, per)
    if problems:
        for line in problems:
            print(f"{RED}台账损坏{OFF}：{line}", file=sys.stderr)
        return 2

    report(rows)
    tally = {k: sum(1 for r in rows if r["status"] == k) for k in VALID}
    print(f"\n{BOLD}合计 {len(rows)} 项{OFF}  "
          f"{GREEN}{tally['done']} done{OFF} · {tally['wip']} wip · "
          f"{tally['todo']} todo · {tally['dropped']} dropped")

    if args.summary:
        return 0

    faults = audit_done(rows, root)
    if faults:
        print(f"\n{RED}{BOLD}{len(faults)} 个 done 项的闸门立不住：{OFF}")
        for line in faults:
            print(f"  {RED}✗{OFF} {line}")
        return 1
    print(f"{GREEN}每一个 done 项的闸门都存在，且真的被 runner 调用。{OFF}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

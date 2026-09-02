#!/usr/bin/env python3
"""Gate 03 / M2 —— `docs/coverage-gaps.md` 必须与实测的未覆盖行**逐条一致**。

规范 v5.0 §5.3：「未覆盖分支必须逐条列出：`docs/coverage-gaps.md`，每行
「文件:行 · 是什么 · 为什么留」（防御分支 / 不可达 / 待补），与
`--cov-report=term-missing` 一致（闸门核对）。分支覆盖门槛 95% 不变，但
**没有未说明的未覆盖分支**。」

负责人问的是「为什么不是 100%，还差在哪里」。95% 这个数回答不了它；一份
逐行说明可以，**但只有在它是真的时候**。一份写好之后没人核对的说明文件，
半年内一定会与代码分家，而分家的方向恰恰是危险的那一边：代码新增了未覆盖
的分支，文件里没有——于是「已知的洞」看起来还是那几个。

所以两个方向都判未通过：
  * **少写**：实测未覆盖，而文件里没有这一条 → 有人加了一个没人知道的洞；
  * **多写**：文件里写了，而实测已经覆盖 → 说明过期了，它在替一条不存在
    的洞背书，下一次真的出洞时你会以为那就是它。

数据来源（按顺序，取第一个能用的）：
  1. `--coverage-json <file>`：`pytest --cov-report=json` 的产物；
  2. `ci.toml` 的 `python_src_dir` 旁边的 `coverage.json`（约定位置）；
  3. 项目根或 Python 树下的 `coverage.json`。

**不自己跑 pytest。** 一道会跑几分钟测试的闸门会被人从套件里摘掉；而
`coverage.json` 是套件里那一步 pytest 本来就会产出的东西。找不到它时退 2
并说明——那是「还没跑过测试」，不是「没有洞」。

`docs/coverage-gaps.md` 的格式：每条一行，以 `文件:行` 或 `文件:行-行` 开头，
后面跟说明。行号可以写成区间（`kernel/beam.py:120-124`）。空行与 Markdown
标题、表头忽略。

    python tools/ci/check_coverage_gaps.py [--root .] [--coverage-json F]
                                           [--self-test]

退出码：0 通过 · 1 未通过 · 2 本阶段尚不适用。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci_config import checked, load as load_config          # noqa: E402

#: 一行说明。三种写法：
#:
#:   `路径:行`            一条完全没执行的语句
#:   `路径:行-行`         连续的一段
#:   `路径:L行→行`        一条部分覆盖的弧（判断执行过，这一条去向没走过）
#:
#: 第三种是 term-missing 里 `L1->L2` 的写法。它必须被认得，否则一份按
#: term-missing 逐条抄下来的说明文件会整批被判成「没写」。
ENTRY = re.compile(
    r"^\s*(?:[-*+]\s*|\|\s*)?`?([\w./\\-]+\.py):"
    r"(?:L(\d+)\s*(?:→|->|—>)\s*(?:exit|\d+)"          # 弧
    r"|(\d+)(?:\s*[-–]\s*(\d+))?)`?")                  # 语句或区间


def declared(text: str) -> dict[str, set[int]]:
    """说明文件里声明的未覆盖行。"""
    out: dict[str, set[int]] = {}
    for line in text.splitlines():
        match = ENTRY.match(line)
        if not match:
            continue
        # 是条目，还是一句顺带举例的正文？
        #
        # 说明文件的正文会写「…例如 a.py:158、b.py:163、c.py:9 …」，那种句子
        # 以缩进加反引号开头，长得和条目一模一样，第一版把它当成了三条声明。
        # 而**条目自己的说明文字里也会引到别的文件**（「与 solve/beam.py:47
        # 同一个原因」），所以「一行只许提一处」这条判据一试就把真条目也杀了。
        #
        # 判据落在【有没有列表记号】上：条目是列表项或表格行，正文不是。
        # 没有记号时（自检里的裸行写法）才退回「整行只提一处」。
        marker = re.match(r"\s*(?:[-*+]\s|\|)", line)
        if not marker and len(re.findall(r"[\w./\\-]+\.py:", line)) > 1:
            continue
        path = match.group(1)
        if match.group(2):                       # 弧：登记它的**起点**
            lines = {int(match.group(2))}
        else:
            start = int(match.group(3))
            last = int(match.group(4)) if match.group(4) else start
            lines = set(range(start, last + 1))
        out.setdefault(normalise(path), set()).update(lines)
    return out


def normalise(path: str) -> str:
    """路径比对只看**包内的相对部分**。

    coverage.json 存的可能是绝对路径、也可能是相对 pytest 工作目录的；
    说明文件里的人写的通常是 `mechanicskit/kernel/beam.py` 或
    `python/src/mechanicskit/kernel/beam.py`。三种写法指的是同一个文件，
    而按整串比对会把它们判成三个不同的文件、然后同时报「少写」和「多写」。
    """
    text = str(path).replace("\\", "/")
    for prefix in ("python/src/", "src/", "./"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    return text


def same_file(a: str, b: str) -> bool:
    """两条路径指的是同一个文件吗。

    实测那边来自 coverage.json，带包名（`mechanicskit/composition/axial.py`）；
    人写说明时常常省掉包名（`composition/axial.py`），因为一份说明文件里
    每一行都以同一个包名开头没有信息量。按【后缀】比对，不按整串。

    只在其中一条是另一条的路径后缀时才算同一个文件——`beam.py` 与
    `kernel/beam.py` 算同一个，`solve/beam.py` 与 `kernel/beam.py` 不算。
    """
    if a == b:
        return True
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    return long.endswith("/" + short)


def measured(report: dict) -> dict[str, set[int]]:
    """coverage.json 里**需要一条说明**的行。

    两种缺口：一条完全没执行的语句，和一条部分覆盖的弧（判断执行过，某一条
    去向没走过）。弧按它的**起点**登记，因为说明文件里的 `L1→L2` 写的就是
    起点。

    有一条去重规则：**当一条弧的去向本身就是一条没执行的语句时，它不算独立
    的缺口。** `if x <= 0: return nan` 这个守卫从未执行时，coverage 会同时
    报「第 67 行没执行」和「66→67 这条弧没走过」——那是同一个洞的两种记法，
    要求写两条说明，只会逼人把同一句话抄两遍，而抄两遍的文件没人愿意维护。
    这条规则是 M-A7 写说明文件时自己定下的，闸门跟着它，而不是反过来。
    """
    out: dict[str, set[int]] = {}
    for path, entry in (report.get("files") or {}).items():
        statements = set(entry.get("missing_lines") or [])
        arcs = [b for b in (entry.get("missing_branches") or [])
                if isinstance(b, (list, tuple)) and len(b) >= 2]
        needed = set(statements)
        for source, destination in ((b[0], b[1]) for b in arcs):
            if destination not in statements:
                needed.add(source)
        if needed:
            out[normalise(path)] = needed
    return out


def compare(measured_lines: dict[str, set[int]],
            declared_lines: dict[str, set[int]]):
    """(少写的, 多写的)，各自展开成 `文件:行`。

    参数顺序是【实测在前，说明在后】，返回也按这个顺序读：
      * 少写 = 实测有、说明里没有 —— 有人加了一个没人知道的洞；
      * 多写 = 说明里有、实测没有 —— 说明过期，在替一条不存在的洞背书。

    第一版把两个方向的名字取反了，自检当场抓到——两个方向的清单长得一样，
    只有名字能区分它们，而名字取反的报告会把「新增的洞」说成「已经补上了」。
    """
    undocumented: list[str] = []
    stale: list[str] = []

    # 文件按【路径后缀】配对，不按整串——见 same_file。配错一次的后果是
    # 同一个文件同时出现在「少写」和「多写」里，读起来像两个问题。
    pairs: dict[str, str] = {}
    for m_path in measured_lines:
        for d_path in declared_lines:
            if same_file(m_path, d_path):
                pairs[m_path] = d_path
                break

    for path in sorted(measured_lines):
        m = measured_lines[path]
        d = declared_lines.get(pairs.get(path, path), set())
        undocumented += [f"{path}:{n}" for n in sorted(m - d)]

    matched = set(pairs.values())
    for path in sorted(declared_lines):
        d = declared_lines[path]
        source = next((mp for mp, dp in pairs.items() if dp == path), None)
        m = measured_lines.get(source, set()) if source else set()
        if path not in matched and source is None:
            m = set()
        stale += [f"{path}:{n}" for n in sorted(d - m)]
    return undocumented, stale


# ──────────────────────────────── 自检 ────────────────────────────────

REPORT = {"files": {
    "python/src/kit/kernel/beam.py": {"missing_lines": [120, 121],
                                      "missing_branches": [[88, 90]]},
    "python/src/kit/solve/root.py": {"missing_lines": [], "missing_branches": []},
}}


def self_test() -> int:
    ok = True
    truth = measured(REPORT)

    complete = ("kit/kernel/beam.py:88 防御分支\n"
                "kit/kernel/beam.py:120-121 不可达\n")
    undocumented, stale = compare(measured(REPORT), declared(complete))
    good = not undocumented and not stale
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  放行  逐条一致（含区间写法）"
          + ("" if good else f"   ← 少写 {undocumented} 多写 {stale}"))

    thin = "kit/kernel/beam.py:120 不可达\n"
    undocumented, stale = compare(measured(REPORT), declared(thin))
    good = (sorted(undocumented)
            == ["kit/kernel/beam.py:121", "kit/kernel/beam.py:88"]
            and not stale)
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  抓到  **少写**：实测有洞而文件里没有")

    fat = ("kit/kernel/beam.py:88 防御\nkit/kernel/beam.py:120-121 不可达\n"
           "kit/solve/root.py:7 早就补上了的一条\n")
    undocumented, stale = compare(measured(REPORT), declared(fat))
    good = stale == ["kit/solve/root.py:7"] and not undocumented
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  抓到  **多写**：说明过期，"
          f"在替一条不存在的洞背书")

    absolute = "python/src/kit/kernel/beam.py:88\n"
    good = "kit/kernel/beam.py" in declared(absolute)
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  归一  三种路径写法指同一个文件")

    good = not declared("# 未覆盖分支\n\n| 文件 | 说明 |\n|---|---|\n")
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  忽略  标题与表头不算条目")

    good = bool(truth) and len(truth) == 1
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  解析  全覆盖的文件不进未覆盖表")

    prose = ("  这一段是正文，顺带举了三个例子："
             "`kit/kernel/beam.py:120`、`kit/solve/root.py:7`、`kit/g.py:1`。\n")
    good = not declared(prose)
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  忽略  没有列表记号、又提到多处的是正文"
          + ("" if good else f"   ← {declared(prose)}"))

    # 而条目的说明文字里引到别的文件，仍然是条目。第一版的判据在这里
    # 把真条目也杀了，报出一条根本没人碰过的「少写」。
    cross = "- `kit/kernel/beam.py:88` — 不可达：与 `kit/solve/root.py:7` 同一个原因\n"
    good = declared(cross) == {"kit/kernel/beam.py": {88}}
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  保住  条目的说明里引到别的文件"
          + ("" if good else f"   ← {declared(cross)}"))

    # 弧的写法：`L88→90` 登记起点 88，与 term-missing 的 `88->90` 对应。
    arc = ("kit/kernel/beam.py:L88→90 防御\n"
           "kit/kernel/beam.py:120-121 不可达\n")
    undocumented, stale = compare(measured(REPORT), declared(arc))
    good = not undocumented and not stale
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  接受  弧的写法 `L1→L2`"
          + ("" if good else f"   ← 少写 {undocumented} 多写 {stale}"))

    # 去重规则：弧的去向本身就是没执行的语句时，只要求一条说明，不要求两条。
    dedup_report = {"files": {"src/kit/g.py": {
        "missing_lines": [67], "missing_branches": [[66, 67]]}}}
    good = measured(dedup_report) == {"kit/g.py": {67}}
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  去重  守卫体没执行时，"
          f"「行」与「通往它的弧」是同一个洞"
          + ("" if good else f"   ← {measured(dedup_report)}"))

    # 而去向【执行过】的弧仍然是独立的洞，必须自己有一条说明。
    live_report = {"files": {"src/kit/h.py": {
        "missing_lines": [], "missing_branches": [[10, 20]]}}}
    good = measured(live_report) == {"kit/h.py": {10}}
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  不去重  去向执行过的弧"
          f"仍然要有自己的说明")

    # 后缀配对：省掉包名的写法要认，但不同目录的同名文件不能混为一谈。
    good = (same_file("mechanicskit/composition/axial.py",
                      "composition/axial.py")
            and not same_file("kit/solve/beam.py", "kit/kernel/beam.py"))
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  后缀  省掉包名算同一个文件，"
          f"同名不同目录不算")

    print("\n自检通过——闸门两个方向都在工作" if ok else "\n自检失败")
    return 0 if ok else 1


def find_report(root: Path, cfg, explicit: Path | None) -> Path | None:
    if explicit:
        return explicit if explicit.is_file() else None
    candidates: list[Path] = []
    src = cfg.path("python_src_dir")
    if src:
        candidates.append(src.parent / "coverage.json")
    candidates += [root / "coverage.json", root / "python" / "coverage.json"]
    for path in candidates:
        if path.is_file():
            return path
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--coverage-json", type=Path, default=None)
    ap.add_argument("--gaps", type=Path, default=None,
                    help="说明文件；不给就读 ci.toml 的 coverage_gaps")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        print("check_coverage_gaps.py 自检")
        return self_test()

    root = args.root.resolve()
    cfg = load_config(root)
    gaps_path = args.gaps or cfg.path("coverage_gaps") \
        or (root / "docs" / "coverage-gaps.md")
    report_path = find_report(root, cfg, args.coverage_json)

    if report_path is None:
        print("尚不适用：找不到 coverage.json —— 先跑一次 "
              "`pytest --cov --cov-branch --cov-report=json:coverage.json`。",
              file=sys.stderr)
        print("  这道闸门不自己跑 pytest：一道要跑几分钟测试的闸门"
              "会被人从套件里摘掉。", file=sys.stderr)
        return 2

    report = json.loads(report_path.read_text(encoding="utf-8"))
    truth = measured(report)

    if not gaps_path.is_file():
        total = sum(len(v) for v in truth.values())
        print(f"✗ 没有 {gaps_path.relative_to(root) if gaps_path.is_relative_to(root) else gaps_path}，"
              f"而实测有 {total} 行未覆盖，分布在 {len(truth)} 个文件里。")
        print("  规范 v5.0 §5.3：没有未说明的未覆盖分支。"
              "负责人问的是「为什么不是 100%，还差在哪里」——"
              "答案必须能直接从这份文件读出来。")
        print("  每行写「文件:行 · 是什么 · 为什么留」"
              "（防御分支 / 不可达 / 待补）。")
        return 1

    want = declared(gaps_path.read_text(encoding="utf-8"))
    undocumented, stale = compare(truth, want)
    total = sum(len(v) for v in truth.values())
    print(checked(total, "行实测未覆盖",
                  f"说明文件里 {sum(len(v) for v in want.values())} 行 · "
                  f"来源 {report_path.name}"))

    if total == 0 and not want:
        print("✓ 实测零行未覆盖，说明文件也是空的——两边一致")
        return 0

    failed = False
    if undocumented:
        print(f"✗ **少写** {len(undocumented)} 行：实测未覆盖，而说明文件里没有")
        for line in undocumented[:25]:
            print(f"    {line}")
        if len(undocumented) > 25:
            print(f"    …… 另 {len(undocumented) - 25} 行")
        print("  有人加了一个没人知道的洞。")
        failed = True
    if stale:
        print(f"✗ **多写** {len(stale)} 行：说明文件里有，而实测已经覆盖")
        for line in stale[:25]:
            print(f"    {line}")
        if len(stale) > 25:
            print(f"    …… 另 {len(stale) - 25} 行")
        print("  说明过期了，它在替一条不存在的洞背书——"
              "下一次真的出洞时你会以为那就是它。")
        failed = True

    if failed:
        return 1
    print(f"✓ {total} 行未覆盖，与说明文件逐条一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())

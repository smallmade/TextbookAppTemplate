#!/usr/bin/env python3
"""Gate 02 —— 输入格式矩阵校验。

    python check_input_matrix.py <项目目录> [--reader "cmd {file}"] [--expect-rows 6]

三件事，一件比一件有价值：

  1. 矩阵齐备          —— 成对覆盖完整，已知致命组合一个不少
  2. fixture 未被改坏  —— 逐字节比对，专防 git 把 CRLF 悄悄改成 LF
  3. **读取器真的读得进去** —— 用 --reader 把 App 的读取器接进来实测

第 3 件是这道闸门的全部意义。前两件只保证「测试数据是对的」，只有第三件
回答「App 读不读得了」——而 PlotOne 栽的正是后者：样例文件本身没问题，是
读取器按 `\\n` 切行，含 CRLF 的文件整份被当作一行。

──────────────────────────────────────────────────────────────────────
git 会悄悄毁掉这些 fixture
──────────────────────────────────────────────────────────────────────

`core.autocrlf` 与 `text=auto` 会在检出时把 CRLF 规范化成 LF。**一个专门用来
测 CRLF 的 fixture 被 git 改成 LF，测试照样绿灯，而缺陷原样还在。**

所以项目根目录必须有 .gitattributes：

    tests/data/matrix/** -text -diff

这道检查会核对它在不在。

──────────────────────────────────────────────────────────────────────
--reader 怎么写
──────────────────────────────────────────────────────────────────────

给一条命令，`{file}` 会被替换成 fixture 路径。约定：读得进去就退出 0，并在
标准输出里打印解析出的**数据行数**（不含表头）。读不进去就非 0 退出。

    # Python 侧
    --reader "python -c 'import sys;from beamkit.io import read;print(len(read(sys.argv[1])))' {file}"

    # Swift 侧（用 Verify 目标）
    --reader "swift/.build/debug/BeamKitVerify --count-rows {file}"

退出码：0 通过 · 1 未通过 · 2 本阶段尚不适用
"""

from __future__ import annotations

import argparse
import itertools
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from make_input_matrix import (DEADLY, DIMENSION_KEYS, render,
                                   representable)  # type: ignore
except ImportError:                       # 旧版生成器的回退
    from make_input_matrix import DEADLY, render  # type: ignore
    DIMENSION_KEYS = ["line_ending", "encoding", "delimiter", "header", "numeric"]
    def representable(le: str, enc: str) -> bool:  # noqa: E306
        return True

RED, GREEN, YELLOW, BOLD, OFF = (
    "\033[31m", "\033[32m", "\033[33m", "\033[1m", "\033[0m")


def load_manifest(matrix_dir: Path) -> list[dict] | None:
    p = matrix_dir / "MANIFEST.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


# ── 检查 1：矩阵齐备 ─────────────────────────────────────────────

def check_completeness(manifest: list[dict]) -> list[str]:
    problems: list[str] = []

    values = {d: sorted({r[d] for r in manifest}) for d in DIMENSION_KEYS}
    # 不可表示的组合不该被要求覆盖——U+2028 在 Latin-1 里根本不存在。
    # 生成器会剔除它们，检查器必须用同一条规则，否则会把「剔除」报成「缺失」。
    def pair_is_possible(a: str, x: str, b: str, y: str) -> bool:
        """只有「换行符 × 编码」这一对才可能不可表示，其余永远可能。"""
        pair = {a: x, b: y}
        le, enc = pair.get("line_ending"), pair.get("encoding")
        return representable(le, enc) if (le and enc) else True

    need = {
        (a, x, b, y)
        for a, b in itertools.combinations(DIMENSION_KEYS, 2)
        for x in values[a] for y in values[b]
        if pair_is_possible(a, x, b, y)
    }
    have = {
        (a, r[a], b, r[b])
        for r in manifest
        for a, b in itertools.combinations(DIMENSION_KEYS, 2)
    }
    missing = need - have
    if missing:
        problems.append(f"成对覆盖不完整：{len(missing)} / {len(need)} 对没有 fixture")
        for a, x, b, y in sorted(missing)[:8]:
            problems.append(f"    {a}={x} 与 {b}={y} 没有一起出现过")

    present = {r["file"] for r in manifest}
    for d in DEADLY:
        combo = tuple(d[:5])
        name = "_".join(combo) + ".csv"
        if name not in present:
            problems.append(f"缺少已知致命组合 {name} —— {d[5]}")
    return problems


# ── 检查 2：fixture 未被改坏 ─────────────────────────────────────

def check_bytes(matrix_dir: Path, manifest: list[dict], rows: int) -> list[str]:
    """逐字节比对。专防 git autocrlf 把 CRLF fixture 悄悄改成 LF。"""
    problems: list[str] = []
    for r in manifest:
        f = matrix_dir / r["file"]
        if not f.exists():
            problems.append(f"{r['file']} 不见了")
            continue
        expected = render(r["line_ending"], r["encoding"], r["delimiter"],
                          r["header"], r["numeric"], rows)
        actual = f.read_bytes()
        if actual == expected:
            continue
        # 最常见的一种损坏值得单独点名
        if r["line_ending"] == "crlf" and b"\r\n" not in actual and b"\n" in actual:
            problems.append(
                f"{r['file']} 的 CRLF 已被改成 LF —— 多半是 git core.autocrlf 或 "
                f"text=auto 干的。**一个专门用来测 CRLF 的 fixture 被改成 LF，"
                f"测试照样绿灯，而缺陷原样还在。**")
        elif r["encoding"] == "utf8bom" and not actual.startswith(b"\xef\xbb\xbf"):
            problems.append(f"{r['file']} 的 BOM 不见了")
        else:
            problems.append(f"{r['file']} 内容与生成规则不符（可能被手工改过）")
    return problems


def check_gitattributes(project: Path) -> list[str]:
    ga = project / ".gitattributes"
    want = "tests/data/matrix"
    if not ga.exists() or want not in ga.read_text(encoding="utf-8", errors="ignore"):
        return [
            "缺少 .gitattributes 里对 tests/data/matrix 的保护 —— 请加一行：\n"
            "        tests/data/matrix/** -text -diff\n"
            "      否则 git 会在检出时把 CRLF 规范化成 LF，"
            "而这批 fixture 测的就是 CRLF"
        ]
    return []


# ── 检查 3：读取器真的读得进去 ──────────────────────────────────

def check_reader(matrix_dir: Path, manifest: list[dict],
                 reader: str, expect_rows: int) -> tuple[list[str], int]:
    problems: list[str] = []
    ok = 0
    for r in manifest:
        f = matrix_dir / r["file"]
        cmd = reader.replace("{file}", str(f))
        try:
            proc = subprocess.run(cmd, shell=True, capture_output=True,
                                  text=True, timeout=30)
        except subprocess.TimeoutExpired:
            problems.append(f"{r['file']}: 读取器超时（30s）")
            continue
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout).strip().splitlines()
            why = tail[-1] if tail else f"退出码 {proc.returncode}"
            note = f" ← {r['why']}" if r.get("deadly") else ""
            problems.append(f"{r['file']}: 读不进去 —— {why}{note}")
            continue
        out = proc.stdout.strip().splitlines()
        digits = [ln for ln in out if ln.strip().lstrip("-").isdigit()]
        if digits and int(digits[-1]) != expect_rows:
            note = f" ← {r['why']}" if r.get("deadly") else ""
            problems.append(
                f"{r['file']}: 解析出 {digits[-1]} 行，应为 {expect_rows} 行{note}")
            continue
        ok += 1
    return problems, ok


# ── 主 ────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", type=Path, nargs="?", default=Path("."))
    ap.add_argument("--reader", help='读取器命令，{file} 会被替换成 fixture 路径')
    ap.add_argument("--expect-rows", type=int, default=6)
    args = ap.parse_args()

    project = args.project.resolve()
    matrix_dir = project / "tests" / "data" / "matrix"
    if not matrix_dir.is_dir():
        print("尚不适用：还没有 tests/data/matrix/ —— 先跑 make_input_matrix.py",
              file=sys.stderr)
        return 2
    manifest = load_manifest(matrix_dir)
    if manifest is None:
        print("尚不适用：matrix/ 里没有 MANIFEST.json —— 用 make_input_matrix.py 生成",
              file=sys.stderr)
        return 2

    print()
    print(f"{BOLD}Gate 02 · 输入格式矩阵{OFF}")
    print()

    fail = 0

    comp = check_completeness(manifest)
    if comp:
        print(f"  {RED}✗{OFF} 矩阵齐备")
        for p in comp:
            print(f"      {p}")
        fail += 1
    else:
        n_deadly = sum(1 for r in manifest if r.get("deadly"))
        print(f"  {GREEN}✓{OFF} 矩阵齐备  {len(manifest)} 个 fixture，"
              f"成对覆盖完整，{n_deadly} 个已知致命组合齐")

    integrity = check_bytes(matrix_dir, manifest, args.expect_rows)
    integrity += check_gitattributes(project)
    if integrity:
        print(f"  {RED}✗{OFF} fixture 完整性")
        for p in integrity[:10]:
            print(f"      {p}")
        if len(integrity) > 10:
            print(f"      …… 另有 {len(integrity) - 10} 项")
        fail += 1
    else:
        print(f"  {GREEN}✓{OFF} fixture 完整性  逐字节与生成规则一致，"
              f".gitattributes 已保护")

    if args.reader:
        problems, ok = check_reader(matrix_dir, manifest,
                                    args.reader, args.expect_rows)
        if problems:
            print(f"  {RED}✗{OFF} 读取器实测  {ok} / {len(manifest)} 个读得进去")
            for p in problems[:15]:
                print(f"      {p}")
            if len(problems) > 15:
                print(f"      …… 另有 {len(problems) - 15} 项")
            fail += 1
        else:
            print(f"  {GREEN}✓{OFF} 读取器实测  {ok} / {len(manifest)} 个全部正确读入")
    else:
        print(f"  {YELLOW}−{OFF} 读取器实测  未提供 --reader")
        print(f"      **这是本闸门最有价值的一项。** 前两项只保证测试数据是对的，")
        print(f"      只有这一项回答「App 读不读得了」—— 而 PlotOne 栽的正是后者。")

    print()
    if fail:
        print(f"{RED}{BOLD}未通过：{fail} 项。{OFF}\n")
        return 1
    print(f"{GREEN}{BOLD}输入格式矩阵通过。{OFF}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

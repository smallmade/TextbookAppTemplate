#!/usr/bin/env python3
"""Gate 02 —— 七条充分性判据。

    python check_sufficiency.py <项目目录> [--package <目录>] [--json]
                                [--strict-examples]

`spec/` 在项目根；`tests/` 与 `src/` 可以在根，也可以在一个子目录里
（本系列的 Python 端住在 `python/`）。`--package` 指定那个子目录，不给就
自动找。**这一条是被同一个 bug 咬第二次之后加的**：`check_input_matrix.py`
当年也假设扁平布局，把一个正确的仓库报成「缺失」。这次更糟——这个脚本报的
是「尚不适用」，退出码 2，于是它在整个开发期都显示为一行黄色的「跳过」，
七条判据一条也没跑过。

规范里「确保验证充分，减少发布后的纠错」这句话的可执行形式。七条判据全部
对着**正典**核对**实际存在的 fixture**，而不是对着一份手写清单——手写清单
谎报覆盖率已经发生过一次（移植清单是手写元组，两个模块没进元组，报告显示
「79/79 已移植」）。

──────────────────────────────────────────────────────────────────────
目录约定
──────────────────────────────────────────────────────────────────────

这套检查需要知道「哪个 fixture 属于哪个 module、哪一层」。约定用目录编码，
因为目录是文件系统里唯一不会和内容不同步的元数据：

    tests/data/
      layer1-printed/<module_id>[-<suffix>].csv      层 1 印刷表格（4 位）
      layer2-highprec/<module_id>[-<suffix>].csv     层 2 高精度（20 位）
      layer2-highprec/generate_<module_id>.py        层 2 的生成脚本
      layer3-symbolic/<module_id>[-<suffix>].py      层 3 符号验证
      layer5-secondsource/<module_id>[-<suffix>].csv 层 5 独立第二源
      examples/<module_id>.csv                       教材章内例题
      SOURCE.md                                      联网 fixture 的留证

层 4（性质测试）不放 fixture ——它由正典的 invariants / trends / boundaries
自动派生，所以这里核对的是「正典里有没有声明」和「测试里有没有引用」。

<suffix> 是可选的，用来给同一个 module 放多个 fixture（如 `beam-cantilever`
与 `beam-simply-supported`）。第一个连字符之前的部分就是 module id。

──────────────────────────────────────────────────────────────────────
退出码
──────────────────────────────────────────────────────────────────────

    0  七条全过
    1  有判据未满足
    2  本阶段尚不适用（正典还没写模块，或 tests/data 还不存在）

第三种是必要的：一道在 fixture 还没建时就报「通过」的闸门是静默放行。
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ── 目录约定 ──────────────────────────────────────────────────────

LAYER_DIRS = {
    1: "layer1-printed",
    2: "layer2-highprec",
    3: "layer3-symbolic",
    5: "layer5-secondsource",
}
EXAMPLES_DIR = "examples"

# 层 2 的生成脚本绝不能 import 核心（黄金律）。这些名字之外的 import 才算。
GENERATOR_PREFIX = "generate_"


# ── 结果模型 ──────────────────────────────────────────────────────

@dataclass
class Criterion:
    #: Usually an int. "1b" is a string, because the printed-table criterion
    #: split in two -- appendix tables and worked examples prove different
    #: things and are counted apart -- and renumbering everything below it
    #: would have broken every reference to "judgement 6" in the docs.
    number: int | str
    title: str
    detail: str = ""
    passed: bool = False
    misses: list[str] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""


@dataclass
class Findings:
    criteria: list[Criterion] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def failed(self) -> list[Criterion]:
        return [c for c in self.criteria if not c.passed and not c.skipped]

    @property
    def skipped(self) -> list[Criterion]:
        return [c for c in self.criteria if c.skipped]


# ── 正典读取 ──────────────────────────────────────────────────────

def find_package(project: Path, given: Path | None) -> Path:
    """`tests/` 与 `src/` 住在哪。

    先看命令行，再看项目根，最后找恰好一个含 `tests/data/` 的子目录。
    「恰好一个」是有意的：找到两个就说不清是哪一个，而猜错会让这道闸门对着
    空目录报「尚不适用」——那正是它上一次失效的方式。
    """
    if given is not None:
        return (project / given).resolve() if not given.is_absolute() else given
    if (project / "tests" / "data").is_dir():
        return project
    candidates = [d for d in sorted(project.iterdir())
                  if d.is_dir() and (d / "tests" / "data").is_dir()]
    return candidates[0] if len(candidates) == 1 else project


def load_spec(project: Path) -> dict | None:
    p = project / "spec" / "specification.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def module_ids(spec: dict) -> list[str]:
    return [m["id"] for m in spec.get("modules", []) if m.get("id")]


# ── fixture 探索 ──────────────────────────────────────────────────

def fixture_modules(data_root: Path, layer: int) -> dict[str, list[Path]]:
    """返回 {module_id: [fixture 文件…]}。自动探索，不读任何清单。"""
    out: dict[str, list[Path]] = {}
    d = data_root / LAYER_DIRS[layer]
    if not d.is_dir():
        return out
    for f in sorted(d.iterdir()):
        if not f.is_file() or f.name.startswith("."):
            continue
        if f.name.startswith(GENERATOR_PREFIX):
            continue
        if f.suffix.lower() not in (".csv", ".json", ".py", ".tsv", ".txt"):
            continue
        mid = f.stem.split("-", 1)[0]
        out.setdefault(mid, []).append(f)
    return out


def example_modules(data_root: Path) -> dict[str, list[Path]]:
    out: dict[str, list[Path]] = {}
    d = data_root / EXAMPLES_DIR
    if not d.is_dir():
        return out
    for f in sorted(d.iterdir()):
        if f.is_file() and f.suffix.lower() in (".csv", ".json", ".tsv"):
            out.setdefault(f.stem.split("-", 1)[0], []).append(f)
    return out


# ── 判据 1、2：层 1 与层 2 覆盖 ──────────────────────────────────

def check_layer_coverage(layer: int, number: int, spec: dict,
                         data_root: Path) -> Criterion:
    """判据 2：每个 module 都要**声明**哪一份高精度 fixture 覆盖它。

    声明而不是靠文件名去猜。一份 fixture 常常覆盖好几个 module——
    `conformance.json` 一份就覆盖十八个 kernel——而文件名的巧合不是一个主张，
    声明才是。**没有声明视为缺口：沉默不算通过。**
    """
    titles = {1: "每个 module ≥1 个层 1 印刷表格点",
              2: "每个 module ≥1 个层 2 高精度点"}
    c = Criterion(number, titles[layer])
    modules = [m for m in spec.get("modules", [])
               if m.get("implemented") is not False]
    if not modules:
        c.skipped, c.skip_reason = True, "正典里还没有 module"
        return c
    have = fixture_modules(data_root, layer)
    for module in modules:
        declared = module.get("layer2") if layer == 2 else None
        if layer == 2:
            if not declared:
                c.misses.append(f"{module['id']}（正典未声明 layer2）")
            elif declared not in have:
                c.misses.append(
                    f"{module['id']} → layer2-highprec/{declared} 不存在")
        elif module["id"] not in have:
            c.misses.append(module["id"])
    c.passed = not c.misses
    c.detail = f"{len(modules) - len(c.misses)} / {len(modules)} 个 module 有覆盖"
    return c


def check_printed_tables(spec: dict, data_root: Path) -> Criterion:
    """判据 1：凡【存在可抽样印刷表】的 module，都要有层 1 fixture。

    不是 54/54。层 1 的定义是「教材附录表」，而附录表只存在于性质、临界
    常数、热化学数据与平衡常数——不存在「Rankine 循环效率表」。要求每个
    module 都有一个，只会逼出把例题答案伪装成表格数据，那比缺口更糟。

    所以正典逐个模块声明 `printed_table`：要么指向它用的 fixture，要么写
    false 并说明理由。没有声明的模块视为缺口——沉默不算通过。
    """
    c = Criterion(1, "凡有印刷表可抽样的 module 都有层 1 点")
    modules = [m for m in spec["modules"] if m.get("implemented") is not False]
    if not modules:
        c.skipped, c.skip_reason = True, "正典里还没有 module"
        return c

    undeclared = [m["id"] for m in modules if "printed_table" not in m]
    have = fixture_modules(data_root, 1)
    expected = [(m["id"], m["printed_table"]) for m in modules
                if m.get("printed_table")]

    c.misses = [f"{mid}（正典未声明 printed_table）" for mid in undeclared]
    c.misses += [f"{mid} → layer1-printed/{stem}.csv 不存在"
                 for mid, stem in expected if stem not in have]
    c.passed = not c.misses
    without = len(modules) - len(expected)
    c.detail = (f"{len(expected) - len([1 for mid, s in expected if s not in have])}"
                f" / {len(expected)} 个「有表」module 有覆盖"
                f"（另 {without} 个无表可抽，见判据 1b）")
    return c


def check_worked_examples(spec: dict, data_root: Path) -> Criterion:
    """判据 1b：凡【无印刷表】的 module，都要有印有答案的章内例题。

    与判据 1 分开计数，因为两者证明的不是同一件事。附录表是一组独立于任何
    题目的数值；例题答案是一个具体工况算完的结果。两者都独立于本程序的
    算术，这是层 1 存在的理由；但把它们混成一个数字，就再也看不出哪些模块
    只有例题、哪些真的对过表。
    """
    c = Criterion("1b", "凡无印刷表的 module 都有印刷例题答案")
    modules = [m for m in spec["modules"] if m.get("implemented") is not False]
    if not modules:
        c.skipped, c.skip_reason = True, "正典里还没有 module"
        return c

    d = data_root / EXAMPLES_DIR
    have = set()
    if d.is_dir():
        for f in sorted(d.iterdir()):
            if f.is_file() and f.suffix.lower() in (".csv", ".json"):
                have.add(f.stem.split("-", 1)[0])

    expected = [m["id"] for m in modules if not m.get("printed_table")]
    # 明写「本项目手头的来源里没有印刷例题」的模块不算缺口——但必须写明
    # 理由，而且要在报告里看得见。沉默地跳过和明写地跳过是两回事。
    unavailable = [m["id"] for m in modules
                   if not m.get("printed_table")
                   and m.get("printed_example") is False
                   and len(str(m.get("printed_example_note", ""))) > 40]
    # 写了 false 却不写理由的，仍然算缺口。这段注释原本说「必须写明理由」
    # 而没有检查它——一条只写在注释里的规则不是规则。
    silent = [m["id"] for m in modules
              if m.get("printed_example") is False
              and len(str(m.get("printed_example_note", ""))) <= 40]
    c.misses = [f"{mid}（写了无例题却没写理由）" for mid in silent]
    c.misses += [mid for mid in expected
                 if mid not in have and mid not in unavailable
                 and mid not in silent]
    c.passed = not c.misses
    covered = len(expected) - len(c.misses) - len(unavailable)
    c.detail = (f"{covered} / {len(expected) - len(unavailable)} 个「无表」"
                f"module 有例题")
    if unavailable:
        c.detail += f"（另 {len(unavailable)} 个明写无例题可用：{', '.join(unavailable)}）"
    return c


# ── 判据 3：性质测试引用了正典 ──────────────────────────────────

def check_property_tests(spec: dict, package: Path) -> Criterion:
    c = Criterion(3, "每个 module ≥1 条 invariant 或 trend 被性质测试执行")
    ids = module_ids(spec)
    if not ids:
        c.skipped, c.skip_reason = True, "正典里还没有 module"
        return c

    # 先看正典里声明了没有——没声明的话，测试再多也派生不出来
    undeclared = [m["id"] for m in spec["modules"]
                  if not m.get("invariants") and not m.get("trends")]
    if undeclared:
        c.misses = [f"{m}（正典里既无 invariant 也无 trend）" for m in undeclared]

    # 再看测试有没有真的读正典派生。裸写的性质测试不算——它会和正典分叉。
    test_text = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in (package / "tests").rglob("*.py")
    ) if (package / "tests").is_dir() else ""
    derives = bool(re.search(r"invariants|trends|boundaries", test_text))
    if not derives and not undeclared:
        c.misses.append(
            "测试里找不到对 invariants / trends / boundaries 的引用 —— "
            "性质必须【从正典派生】，裸写的性质测试会和正典分叉")
    c.passed = not c.misses
    if undeclared:
        c.detail = f"{len(ids) - len(undeclared)} / {len(ids)} 个 module 声明了性质"
    elif not derives:
        c.detail = "正典里都声明了，但测试没有从正典派生"
    else:
        c.detail = f"{len(ids)} 个 module 均已声明并被测试引用"
    return c


# ── 判据 4、5：边界与分支各有测试点 ────────────────────────────

def _spec_derived_points(spec: dict, field_name: str) -> dict[str, list[str]]:
    """本版实际提供的边界／分支。

    条目级的 `"implemented": false` 与模块级的同义：**本版不提供这个选项**。
    一个不出现在界面上的分支不需要测试点——但它必须仍然带着 question 与
    options，好让手册说得出「少了什么」。要求为一个不存在的控件写测试，量的
    还是错的分母。
    """
    out: dict[str, list[str]] = {}
    for m in spec.get("modules", []):
        items = [it for it in (m.get(field_name) or [])
                 if not (isinstance(it, dict) and it.get("implemented") is False)]
        if items:
            out[m["id"]] = [
                (it.get("id") or it.get("name") or str(i))
                if isinstance(it, dict) else str(it)
                for i, it in enumerate(items)
            ]
    return out


def _fixture_text(data_root: Path) -> str:
    if not data_root.is_dir():
        return ""
    chunks = []
    for f in data_root.rglob("*"):
        if f.is_file() and f.suffix.lower() in (".csv", ".tsv", ".json", ".py", ".txt"):
            chunks.append(f.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


def check_derived_points(number: int, field_name: str, label: str,
                         spec: dict, data_root: Path, package: Path) -> Criterion:
    c = Criterion(number, f"每个 {label} 各 ≥1 个测试点")
    declared = _spec_derived_points(spec, field_name)
    if not declared:
        c.skipped = True
        c.skip_reason = f"正典里还没有 {field_name} 声明"
        return c

    haystack = _fixture_text(data_root)
    if (package / "tests").is_dir():
        haystack += "\n".join(
            p.read_text(encoding="utf-8", errors="ignore")
            for p in (package / "tests").rglob("*.py"))

    total = sum(len(v) for v in declared.values())
    for mid, names in declared.items():
        for name in names:
            # 名字出现在 fixture 或测试里，就算有点覆盖它。
            # 这一条粗糙，但它抓的是「声明了却根本没人测」这种整块的遗漏。
            if not re.search(rf"\b{re.escape(name)}\b", haystack):
                c.misses.append(f"{mid}.{name}")
    c.passed = not c.misses
    c.detail = f"{total - len(c.misses)} / {total} 个 {label} 有测试点"
    return c


# ── 判据 6：分支覆盖率 ──────────────────────────────────────────

def check_branch_coverage(roots: list[Path], threshold: float = 95.0) -> Criterion:
    c = Criterion(6, f"分支覆盖率 ≥ {threshold:.0f}%")
    for name in ("coverage.json", ".coverage.json", "htmlcov/status.json"):
        p = next((root / name for root in roots if (root / name).exists()), None)
        if p is None:
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        pct = (data.get("totals", {}) or {}).get("percent_covered")
        if pct is None:
            continue
        c.passed = pct >= threshold
        c.detail = f"实测 {pct:.1f}%"
        if not c.passed:
            c.misses.append(f"分支覆盖率 {pct:.1f}% < {threshold:.0f}%")
        return c
    c.skipped = True
    c.skip_reason = ("没有 coverage.json —— 先跑 "
                     "pytest --cov --cov-branch --cov-report=json")
    return c


# ── 判据 7：教材章内例题 100% ──────────────────────────────────

def check_examples(spec: dict, data_root: Path, strict: bool) -> Criterion:
    c = Criterion(7, "教材章内例题通过率 100%")
    ex = example_modules(data_root)
    if not ex:
        c.skipped = True
        c.skip_reason = f"tests/data/{EXAMPLES_DIR}/ 还没有例题"
        return c
    ids = set(module_ids(spec))
    orphan = [m for m in ex if m not in ids]
    if orphan:
        c.misses += [f"例题 {m} 在正典里找不到对应 module" for m in orphan]
    if strict:
        uncovered = sorted(ids - set(ex))
        c.misses += [f"{m} 没有章内例题" for m in uncovered]
    c.passed = not c.misses
    c.detail = (f"{len(ex)} 个 module 有例题"
                + ("（--strict-examples：要求每个 module 都有）" if strict else ""))
    return c


# ── 黄金律：层 2 生成脚本不得 import 核心 ─────────────────────

def check_golden_rule(package: Path, data_root: Path) -> list[str]:
    """由被测程序产生的 fixture 什么也证明不了。

    层 2 的高精度值必须从教材原式重新打字、以 mpmath 独立计算。这条是整个
    验证体系的地基——违反它，五层里最重要的一层变成自证，而测试永远绿灯。
    """
    problems: list[str] = []
    gen_dir = data_root / LAYER_DIRS[2]
    if not gen_dir.is_dir():
        return problems

    src_pkgs = {p.name for p in (package / "src").iterdir()} \
        if (package / "src").is_dir() else set()

    for f in sorted(gen_dir.glob(f"{GENERATOR_PREFIX}*.py")):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            problems.append(f"{f.name}: 语法错误，无法确认它是否 import 了核心")
            continue
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for n in names:
                root = n.split(".")[0]
                if root in src_pkgs:
                    problems.append(
                        f"{f.name}: import 了核心包 {root!r} —— "
                        f"黄金律：由被测程序产生的 fixture 什么也证明不了")
    return problems


# ── 联网 fixture 留证 ─────────────────────────────────────────

def check_source_records(data_root: Path) -> list[str]:
    """每份联网获取的 fixture 旁边必须有 SOURCE.md。

    没有留证的数据，半年后没有人能回答「这些数字从哪来、精确到几位、
    独立于什么」——而最后一句正是五层阶梯成立的前提。
    """
    problems: list[str] = []
    for layer in (1, 5):          # 这两层最可能来自外部
        d = data_root / LAYER_DIRS[layer]
        if not d.is_dir():
            continue
        has_fixture = any(f.is_file() and f.suffix.lower() in (".csv", ".tsv")
                          for f in d.iterdir())
        if has_fixture and not (d / "SOURCE.md").exists() \
                and not (data_root / "SOURCE.md").exists():
            problems.append(
                f"{LAYER_DIRS[layer]}/ 有 fixture 却没有 SOURCE.md —— "
                f"URL、获取日期、出处名称与许可状态都要留证")
    return problems


# ── 报告 ──────────────────────────────────────────────────────────

RED, GREEN, YELLOW, BOLD, OFF = (
    "\033[31m", "\033[32m", "\033[33m", "\033[1m", "\033[0m")


def render(f: Findings) -> None:
    print()
    print(f"{BOLD}Gate 02 · 七条充分性判据{OFF}")
    print()
    for c in f.criteria:
        if c.skipped:
            mark, colour = "−", YELLOW
            tail = f"  （{c.skip_reason}）"
        elif c.passed:
            mark, colour = "✓", GREEN
            tail = f"  {c.detail}" if c.detail else ""
        else:
            mark, colour = "✗", RED
            tail = f"  {c.detail}" if c.detail else ""
        print(f"  {colour}{mark}{OFF} {c.number}. {c.title}{tail}")
        for m in c.misses[:12]:
            print(f"        {m}")
        if len(c.misses) > 12:
            print(f"        …… 另有 {len(c.misses) - 12} 项")
    if f.notes:
        print()
        print(f"{BOLD}其他{OFF}")
        for n in f.notes:
            print(f"  {RED}✗{OFF} {n}")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", type=Path, nargs="?", default=Path("."))
    ap.add_argument("--package", type=Path, default=None,
                    help="tests/ 与 src/ 所在目录，不给则自动找")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    ap.add_argument("--strict-examples", action="store_true",
                    help="要求每个 module 都有章内例题")
    ap.add_argument("--coverage-threshold", type=float, default=95.0)
    args = ap.parse_args()

    project = args.project.resolve()
    spec = load_spec(project)
    if spec is None:
        print("尚不适用：没有 spec/specification.json —— 阶段 01 之前正常",
              file=sys.stderr)
        return 2
    # 闸门有依赖顺序。正典还是 TODO 骨架时，「每个 module 有没有 fixture」
    # 这个问题没有意义——被问的那个 module 本身还不存在。报「未满足」会让
    # 阶段 01 的正常状态看起来像失败，而真正该修的是正典。
    todo_at = [k for k in ("sources", "meanings", "modules", "validity")
               if "TODO" in json.dumps(spec.get(k, ""), ensure_ascii=False)]
    if todo_at:
        print(f"尚不适用：正典的 {todo_at} 仍含 TODO，Gate 01 未通过 —— "
              f"先把 spec/specification.json 写完", file=sys.stderr)
        return 2

    # 本版不实现的 module 不参与充分性统计。它们已经在正典里明写
    # "implemented": false，由 check_canon_functions.py 强制；对着一个还没写的
    # 实现要求 fixture，量的是错的分母，而且会让这道闸门在整个开发期永远飘红。
    # 规范自己的警告：一个会乱叫的闸门两天之内就会被关掉。
    deferred = [m["id"] for m in spec.get("modules", [])
                if m.get("implemented") is False]
    if deferred:
        spec = dict(spec, modules=[m for m in spec.get("modules", [])
                                   if m.get("implemented") is not False])
        print(f"本版不实现的 {len(deferred)} 个 module 不计入充分性统计："
              f"{' '.join(deferred)}\n"
              f"（它们必须与不做清单一致——这是 Gate 00 的事，不是这里的）\n",
              file=sys.stderr)
    if not spec.get("modules"):
        print("尚不适用：正典里没有任何已实现的 module", file=sys.stderr)
        return 2

    package = find_package(project, args.package)
    data_root = package / "tests" / "data"
    if not data_root.is_dir():
        print(f"尚不适用：{data_root} 不存在 —— 阶段 02 之前正常。\n"
              f"（若 fixture 在别处，用 --package 指出来。这道闸门曾经因为"
              f"假设扁平布局而整个开发期都在「跳过」。）", file=sys.stderr)
        return 2
    if package != project:
        print(f"包目录：{package.relative_to(project)}/\n", file=sys.stderr)

    f = Findings()
    f.criteria.append(check_printed_tables(spec, data_root))
    f.criteria.append(check_worked_examples(spec, data_root))
    f.criteria.append(check_layer_coverage(2, 2, spec, data_root))
    f.criteria.append(check_property_tests(spec, package))
    f.criteria.append(check_derived_points(4, "boundaries", "定义域边界／奇异点",
                                           spec, data_root, package))
    f.criteria.append(check_derived_points(5, "branching", "多解分支",
                                           spec, data_root, package))
    f.criteria.append(check_branch_coverage([project, package],
                                            args.coverage_threshold))
    f.criteria.append(check_examples(spec, data_root, args.strict_examples))
    f.notes += check_golden_rule(package, data_root)
    f.notes += check_source_records(data_root)

    if args.json:
        print(json.dumps({
            "criteria": [{"n": c.number, "title": c.title,
                          "passed": c.passed, "skipped": c.skipped,
                          "detail": c.detail, "misses": c.misses}
                         for c in f.criteria],
            "notes": f.notes,
        }, ensure_ascii=False, indent=2))
    else:
        render(f)

    n_fail = len(f.failed) + (1 if f.notes else 0)
    if n_fail:
        if not args.json:
            print(f"{RED}{BOLD}未满足 {n_fail} 项。{OFF}\n")
        return 1
    if len(f.skipped) == len(f.criteria):
        if not args.json:
            print(f"{YELLOW}全部判据尚不适用 —— 本阶段还没到。{OFF}\n")
        return 2
    if not args.json:
        print(f"{GREEN}{BOLD}七条充分性判据通过"
              f"（跳过 {len(f.skipped)} 项尚不适用的）。{OFF}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Gate 02 —— 生成输入格式矩阵的 fixture。

    python make_input_matrix.py tests/data/matrix/ [--exhaustive] [--rows N]

──────────────────────────────────────────────────────────────────────
为什么有这个东西
──────────────────────────────────────────────────────────────────────

PlotOne 因 Guideline 2.1(a) 被拒——审核员拿到的样例 CSV **一个都导不进去**。

病根：CSV 读取器按 `\\n` 切行，而 Swift 里 CRLF 是**单个扩展字形簇**，含
CRLF 的文件因此整份被当作一行，报出「没有列能解析为数字」——一条指向数字
格式、而问题根本不在那里的错误信息。

CRLF 是 RFC 4180 规定的、也是 Windows 版 Excel 写出的换行符。**这一条缺陷
打掉的是一整类最常见的文件**，而团队自己的测试全部用 Unix 换行，所以从没
碰到过。

「我们的测试数据没覆盖到」不是解释，是这个生成器存在的理由。

──────────────────────────────────────────────────────────────────────
为什么默认不是全笛卡儿积
──────────────────────────────────────────────────────────────────────

五个维度全组合是 5 × 3 × 3 × 2 × 5 = 450 个文件。那么多 fixture 没有人会
去看，跑一次要很久，而且它们中的绝大多数在验证同一件事。

默认生成的是**成对覆盖（pairwise）+ 已知致命组合**，约 40 个文件：

  · 成对覆盖：任意两个维度的任意取值组合，至少出现在一个 fixture 里。
    绝大多数解析缺陷是「两个因素撞在一起」造成的（CRLF 撞上 BOM 就是），
    成对覆盖抓得住这一类，而文件数只有全组合的十分之一。

  · 已知致命组合：CRLF+BOM、CR 单独、制表符+科学记数、空单元格+CRLF 等，
    每一个都对应真实事故或已知的解析陷阱，无条件生成。

需要全组合时加 --exhaustive。它是对的，只是很少值得。
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

# ── 五个维度 ──────────────────────────────────────────────────────

LINE_ENDINGS = {
    "lf":   "\n",          # Unix。团队自己的测试全用这个，所以别的全没测到
    "crlf": "\r\n",        # RFC 4180 与 Windows Excel —— PlotOne 栽在这里
    "cr":   "\r",          # 经典 Mac OS。少见但仍在流通
    "ls":   " ",      # Unicode LINE SEPARATOR
    "ps":   " ",      # Unicode PARAGRAPH SEPARATOR
}

ENCODINGS = {
    "utf8":     ("utf-8", b""),
    "utf8bom":  ("utf-8", b"\xef\xbb\xbf"),   # Windows Excel 另存为 CSV 的默认
    "latin1":   ("latin-1", b""),
}

DELIMITERS = {
    "comma": ",",
    "tab":   "\t",
    "space": "  ",         # 多空格对齐，科学仪器导出常见
}

HEADERS = {"header": True, "noheader": False}

NUMERICS = {
    "int":        lambda i: (f"{i}", f"{i * 2}"),
    "decimal":    lambda i: (f"{i}.25", f"{i * 2}.50"),
    "scientific": lambda i: (f"{i}.0e0", f"{i * 2}.0E+00"),
    "thousands":  lambda i: (f"{i * 1000:,}", f"{i * 2000:,}"),   # 1,000
    "empty":      lambda i: (f"{i}", "" if i % 3 == 1 else f"{i * 2}"),
}

# 每一个都对应真实事故或已知的解析陷阱，无条件生成。
DIMENSION_KEYS = ["line_ending", "encoding", "delimiter", "header", "numeric"]

DEADLY = [
    # (line_ending, encoding, delimiter, header, numeric, 为什么)
    ("crlf", "utf8bom", "comma", "header", "decimal",
     "CRLF 撞上 BOM —— Windows Excel 另存为 CSV 的默认输出"),
    ("crlf", "utf8", "comma", "header", "decimal",
     "纯 CRLF —— PlotOne 被 GL 2.1(a) 拒的直接原因"),
    ("cr", "utf8", "comma", "header", "decimal",
     "单独 CR —— 经典 Mac 行尾，按 \\n 切行时整份变一行"),
    ("crlf", "utf8", "comma", "header", "empty",
     "CRLF 加空单元格 —— 行尾空值容易被吞掉"),
    ("crlf", "utf8", "space", "noheader", "decimal",
     "CRLF 加空白对齐且无表头 —— 仪器导出的典型形状"),
    ("lf", "utf8", "tab", "header", "scientific",
     "制表符加科学记数 —— 分隔符与指数符号都可能被误判"),
    ("lf", "utf8", "comma", "header", "thousands",
     "千分位逗号撞上逗号分隔 —— 引号处理不对就会多出一列"),
    ("ls", "utf8", "comma", "header", "decimal",
     "Unicode LINE SEPARATOR —— Swift 的 .lines 会切，按 \\n 切则不会"),
]


# ── 生成 ──────────────────────────────────────────────────────────

def build_rows(numeric: str, rows: int) -> list[tuple[str, ...]]:
    fn = NUMERICS[numeric]
    return [fn(i) for i in range(1, rows + 1)]


def render(le: str, enc: str, delim: str, header: str,
           numeric: str, rows: int) -> bytes:
    sep = DELIMITERS[delim]
    nl = LINE_ENDINGS[le]
    lines: list[str] = []
    if HEADERS[header]:
        lines.append(sep.join(("x", "y")))

    for a, b in build_rows(numeric, rows):
        # 千分位与逗号分隔撞在一起时必须加引号，否则那一行会多出一列。
        # 这正是这一格要测的东西。
        if numeric == "thousands" and sep == ",":
            a, b = f'"{a}"', f'"{b}"'
        lines.append(sep.join((a, b)))

    text = nl.join(lines) + nl
    codec, bom = ENCODINGS[enc]
    # 不可表示的组合必须报错，不能 errors="replace" 糊过去。
    # 第一版用了 replace，于是 ls/ps 撞上 latin1 时把 U+2028 换成了 '?'，
    # 生成出一个**本身就无效**的 fixture：整份文件变成一行、中间夹个问号，
    # 然后要求读取器把它解析成 6 行——读取器怎么做都是错的。
    # 一个不该存在的测试用例，比没有测试用例更糟。
    return bom + text.encode(codec)


def representable(le: str, enc: str) -> bool:
    """这个换行符能不能在这个编码里表示。

    U+2028 / U+2029 在 Latin-1 里不存在。这类组合直接不生成，而不是生成
    一个内容被替换过的假 fixture。
    """
    codec, _ = ENCODINGS[enc]
    try:
        LINE_ENDINGS[le].encode(codec)
        return True
    except UnicodeEncodeError:
        return False


def name_of(le: str, enc: str, delim: str, header: str, numeric: str) -> str:
    return f"{le}_{enc}_{delim}_{header}_{numeric}.csv"


def pairwise(dims: dict[str, list[str]]) -> list[tuple[str, ...]]:
    """成对覆盖：任意两维的任意取值组合至少出现一次。

    贪心算法——不是最优解，但对五个小维度足够，而且实现短到能一眼读懂。
    最优成对覆盖是 NP-hard，为它引一个依赖不值得。
    """
    keys = list(dims)
    need: set[tuple[int, str, int, str]] = set()
    for i, j in itertools.combinations(range(len(keys)), 2):
        for vi in dims[keys[i]]:
            for vj in dims[keys[j]]:
                need.add((i, vi, j, vj))

    chosen: list[tuple[str, ...]] = []
    # 候选集用全组合，但只在还能消掉未覆盖对时才收下
    for combo in itertools.product(*(dims[k] for k in keys)):
        covers = {(i, combo[i], j, combo[j])
                  for i, j in itertools.combinations(range(len(keys)), 2)}
        gain = covers & need
        if gain:
            chosen.append(combo)
            need -= gain
        if not need:
            break
    return chosen


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dest", type=Path)
    ap.add_argument("--exhaustive", action="store_true",
                    help="生成全笛卡儿积（450 个文件），而非成对覆盖")
    ap.add_argument("--rows", type=int, default=6, help="每个 fixture 的数据行数")
    args = ap.parse_args()

    dims = {
        "line_ending": list(LINE_ENDINGS),
        "encoding":    list(ENCODINGS),
        "delimiter":   list(DELIMITERS),
        "header":      list(HEADERS),
        "numeric":     list(NUMERICS),
    }

    if args.exhaustive:
        combos = list(itertools.product(*dims.values()))
        strategy = "全笛卡儿积"
    else:
        combos = pairwise(dims)
        strategy = "成对覆盖"

    # 已知致命组合无条件加入，去重
    seen = set(combos)
    deadly_combos = [tuple(d[:5]) for d in DEADLY]
    combos += [c for c in deadly_combos if c not in seen]

    # 剔除不可表示的组合。剔掉的要报出来——静默丢弃会让「成对覆盖完整」
    # 这句话变成假的，而检查器正是按这句话判定的。
    dropped = [c for c in combos if not representable(c[0], c[1])]
    combos = [c for c in combos if representable(c[0], c[1])]

    args.dest.mkdir(parents=True, exist_ok=True)
    manifest = []
    for combo in combos:
        le, enc, delim, header, numeric = combo
        name = name_of(*combo)
        (args.dest / name).write_bytes(render(le, enc, delim, header,
                                              numeric, args.rows))
        why = next((d[5] for d in DEADLY if tuple(d[:5]) == combo), "")
        manifest.append({"file": name, "line_ending": le, "encoding": enc,
                         "delimiter": delim, "header": header,
                         "numeric": numeric, "deadly": bool(why),
                         "why": why})

    (args.dest / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    n_deadly = sum(1 for m in manifest if m["deadly"])
    print(f"\n策略：{strategy} + 已知致命组合")
    if dropped:
        print(f"剔除 {len(dropped)} 个不可表示的组合（换行符在该编码里不存在）：")
        for le, enc, *_ in sorted({(c[0], c[1]) for c in dropped}):
            print(f"  · {le} 在 {enc} 里无法表示")
    print(f"生成 {len(manifest)} 个 fixture（其中 {n_deadly} 个是已知致命组合）")
    print(f"→ {args.dest}\n")
    print("每一个都要能被 App 正确读入。「我们的测试数据没覆盖到」不是解释，")
    print("是这个生成器存在的理由。\n")
    print(f"下一步：python tools/ci/check_input_matrix.py {args.dest.parent.parent.parent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

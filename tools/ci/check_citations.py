#!/usr/bin/env python3
"""闸门 —— 抄录层引用的页码，页上必须真的有那个数。

`check_layer5.py` 检查的是**书面纪律**：每一行有没有页码、有没有裁定。它无法
检查页码是不是**对的**——一个写错的页码照样通过，而它比没有页码更糟：它看起来
像证据，查下去却把人带到别处。

这道闸门补上那一半：打开被引用的那一页，确认 `published` 那个数确实印在上面。

    页码正确 → 通过        页码写错 → 未通过        书不在本机 → 跳过并说明

**为什么它可能跳过**：主教材 PDF 存在仓库外（`../Structural Mechanics
Calculator/`，`.gitignore` 已排除 `*.pdf`），公有领域报告也不进仓库。所以这道
闸门在 CI 上会跳过，只有本机跑得动。**跳过时它会说清楚跳过了几行**——静默通过
和明写跳过是两回事。

    python tools/ci/check_citations.py [--root .] [--self-test]

退出码：0 通过 · 1 未通过 · 2 本阶段尚不适用
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from pathlib import Path

GREEN, RED, YELLOW, BOLD, OFF = (
    "\033[32m", "\033[31m", "\033[33m", "\033[1m", "\033[0m")

LAYERS = ("examples", "layer1-printed", "layer5-secondsource")

#: `source` 里的一个词 -> 教材 PDF 的 glob。书在仓库外，按关键词找。
BOOKS = {
    "durka": "*Durka*.pdf",
    "olsson": "*Olsson*.pdf",
    "chajes": "*Chajes*.pdf",
    "bucciarelli": "*Bucciarelli*.pdf",
}


def normalise(text: str) -> str:
    """把一页的文字压成只剩数字与小数点，好让 `17.93` 与 `17. 93` 都能命中。

    扫描件的 OCR 会在数字中间塞进空格与逗号；连字符与中点也常被读成别的东西。
    压掉分隔符不会让匹配变得没有意义——一个五位数字串偶然出现在错的一页上的
    机会很低，而 `--self-test` 拿一个真实的错页证明它确实会拒。
    """
    return re.sub(r"[\s,·’'`]", "", text)


#: 一个值要有多少位数字，出现在某一页上才算得上是证据。
#:
#: 这条门槛是自检逼出来的：第一版拿 `28.0` 当样本，结果它在**偏十页**上也找得到
#: ——`28` 这种两位数在任何一页上都可能出现，找到它什么也没证明。所以短值不是
#: "通过"，是**查不了**，必须单独计数说出来，而不是混进通过数里。
MIN_DIGITS = 4


def digits(value: str) -> int:
    return len(re.sub(r"[^0-9]", "", value))


def variants(value: str) -> list[str]:
    """一个印刷值在页上可能长的几个样子。"""
    out = {value}
    if value.endswith(".0"):
        out.add(value[:-2])
    if "." in value:
        out.add(value.rstrip("0").rstrip("."))
    if value.startswith("0."):
        out.add(value[1:])          # `.425` 这种排版
    return [v for v in out if v]


def read_rows(text: str) -> list[dict[str, str]]:
    body = [line for line in io.StringIO(text) if not line.lstrip().startswith("#")]
    return list(csv.DictReader(body))


def find_book(source: str, refs: Path) -> Path | None:
    low = source.lower()
    for key, pattern in BOOKS.items():
        if key in low:
            hits = sorted(refs.glob(pattern))
            if hits:
                return hits[0]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", type=Path)
    parser.add_argument("--refs", type=Path, default=None)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    refs = args.refs or root.parent / "Structural Mechanics Calculator"

    try:
        from pypdf import PdfReader
    except ImportError:
        print("尚不适用：没有 pypdf，装不了就跑不了这道闸门", file=sys.stderr)
        return 2

    if args.self_test:
        return self_test(root, refs, PdfReader)

    return run(root / "tests" / "data", refs, PdfReader)


def run(data: Path, refs: Path, PdfReader) -> int:
    cache: dict[tuple[str, int], str] = {}
    checked = 0
    skipped_no_book = 0
    too_short = 0
    faults: list[str] = []

    for layer in LAYERS:
        directory = data / layer
        for fixture in sorted(directory.glob("*.csv")) if directory.is_dir() else []:
            for row in read_rows(fixture.read_text(encoding="utf-8")):
                page = (row.get("page_pdf") or "").strip()
                source = (row.get("source") or "").strip()
                published = (row.get("published") or "").strip()
                if not page.isdigit() or not published:
                    continue
                if digits(published) < MIN_DIGITS:
                    too_short += 1
                    continue
                book = find_book(source, refs)
                if book is None:
                    skipped_no_book += 1
                    continue
                key = (str(book), int(page))
                if key not in cache:
                    try:
                        text = PdfReader(str(book)).pages[int(page)].extract_text() or ""
                    except Exception as exc:                      # noqa: BLE001
                        faults.append(f"{fixture.name}: {row.get('tag')}: "
                                      f"读不到 {book.name} 第 {page} 页 — {exc}")
                        cache[key] = ""
                        continue
                    cache[key] = normalise(text)
                flat = cache[key]
                checked += 1
                if not any(v in flat for v in variants(published)):
                    faults.append(
                        f"{fixture.name}: {row.get('tag')}: 引用 {book.name} "
                        f"PDF 第 {page} 页（印刷页 {row.get('page_printed')}），"
                        f"但该页上找不到 {published!r}")

    print()
    print(f"{BOLD}闸门 · 引用的页上有没有那个数{OFF}")
    if checked == 0 and not faults:
        print(f"  {YELLOW}−{OFF} 一行都没查到——教材 PDF 不在 "
              f"{refs}，这道闸门只有本机跑得动")
        print(f"      （另有 {skipped_no_book} 行的来源不是本机的四本书，"
              f"{too_short} 行的数字太短、出现在哪一页都不算证据）")
        print()
        print(f"{YELLOW}尚不适用：找不到可比对的 PDF{OFF}\n", file=sys.stderr)
        return 2

    if faults:
        print(f"  {RED}✗{OFF} {len(faults)} / {checked} 行的页码对不上：")
        for fault in faults[:20]:
            print(f"      {fault}")
        if len(faults) > 20:
            print(f"      …… 另有 {len(faults) - 20} 项")
        print()
        print(f"{RED}{BOLD}未通过。写错的页码比没有页码更糟——它看起来像证据。{OFF}\n")
        return 1

    print(f"  {GREEN}✓{OFF} {checked} 行的页码逐一核对，页上都有那个数")
    if skipped_no_book:
        print(f"  {YELLOW}−{OFF} {skipped_no_book} 行的来源不在本机"
              f"（公有领域报告不进仓库）")
    if too_short:
        print(f"  {YELLOW}−{OFF} {too_short} 行的数字不足 {MIN_DIGITS} 位，"
              f"出现在哪一页都不算证据，这道闸门查不了它们")
    print()
    print(f"{GREEN}{BOLD}引用核对通过。{OFF}\n")
    return 0


def self_test(root: Path, refs: Path, PdfReader) -> int:
    """拿一个真实的错页证明它会拒。

    不是造一个假 CSV——用手上真有的那一页，然后把页码故意写偏十页。一道只在
    自己造的样本上会叫的闸门，不能证明它在真实文件上也会叫。
    """
    fixture = root / "tests" / "data" / "examples" / "retaining_wall.csv"
    if not fixture.is_file():
        print("尚不适用：没有可用来自检的 fixture", file=sys.stderr)
        return 2
    rows = read_rows(fixture.read_text(encoding="utf-8"))
    row = next((r for r in rows if (r.get("page_pdf") or "").isdigit()
                and digits(r.get("published", "")) >= MIN_DIGITS), None)
    book = find_book(row.get("source", ""), refs) if row else None
    if book is None:
        print("尚不适用：自检要用的教材 PDF 不在本机", file=sys.stderr)
        return 2

    right = int(row["page_pdf"])
    published = row["published"]
    ok = True
    for label, page in (("正确的页", right), ("偏十页", right + 10)):
        text = normalise(PdfReader(str(book)).pages[page].extract_text() or "")
        hit = any(v in text for v in variants(published))
        want = (label == "正确的页")
        good = hit == want
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  {label}（{page}）"
              f"{'找到' if hit else '找不到'} {published}")

    print("\n自检通过——闸门确实分得出对页与错页" if ok
          else "\n自检失败——它对错页也不会叫")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

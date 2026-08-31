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

**这道闸门只信十进制字面值，不信分母。** 早先加过一版"分母比对"——`published`
精确重构成简分数时，去页面上找那个分母的数字子串，好应付印的是 `wL^2/12`
而不是 `0.0833333` 的表格。三次自检各抓到它一个坑：

  1. 控制流把"十进制太短"与"分母够不够格"绑在一起，`0.05=1/20` 这种十进制
     只有三位数字、分母却有两位的行，连分母比对的机会都没轮到就被计成查不了。
  2. 对着解出来的具体算例（`examples/` 层，答案就是印在书上的小数）问"它的
     分母在页上吗"，问的是一个源头从没打算回答的问题——`6.73` 的"分母"
     `100` 不是任何人写下来的东西，只是十进制记数法的副产品。
  3. 最根本的一条：`--self-test` 拿 `1/12` 去比对 NASA 手册第 708 页，正确页
     通过，但**偏十页也通过**——不是页眉日期撞上了分母（那个先修过），是那
     一页另一个完全不相干的公式里，恰好也有个分母是 12。一份八百多页、写满
     结构力学公式的手册，`8`、`12`、`20`、`30` 这类"好看"的分母在哪一页都可能
     冒出来，两位数字的门槛从根源上就挡不住这种巧合。

三次里有两次是可以修的实现问题，第三次不是——它说的是"这条证据形式，无论
门槛设多高，都靠不住"。所以现在的设计是：**十进制字面值是唯一自动核对的
证据**（四位数字以上，重复出现在无关页面的机会小到可以忽略）；印的是分数、
或者这份扫描件在这个位置文字层本身坏掉的行，一律要求 `verified_by_eye`
——人看着渲染出来的页面图核对过，理由写进 SOURCE.md，闸门核对的是"这行
理由真的记在案"，不是去赌一个孤零零的数字不会在别处重复。

    python tools/ci/check_citations.py [--root .] [--self-test]

退出码：0 通过 · 1 未通过 · 2 本阶段尚不适用
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from fractions import Fraction
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
    "nasa": "*Astronautic*.pdf",
    "astronautic": "*Astronautic*.pdf",
    "tm x-73305": "*Astronautic*.pdf",
}

#: 每一页重复印着的页眉——文件名、日期、页码——不是这一页的内容，是这份
#: PDF 每一页都有的装订线。留着它们，一个短数字去撞上日期或页码的机会高得
#: 不像话：第一版自检就撞见页眉印着「12 September 1961」，把无关日期里的
#: `12` 当成了内容。剥掉页眉再比对，问的才是"这一页的内容里有没有这个数"。
BOILERPLATE = re.compile(
    r"^Section\s+\w+\s*\d*$"
    r"|^Page\s*\d+$"
    r"|^\d{1,2}\s+(January|February|March|April|May|June|July|August"
    r"|September|October|November|December)\s+\d{4}$"
    r"|^(January|February|March|April|May|June|July|August|September"
    r"|October|November|December)\s+\d{1,2},?\s+\d{4}$",
    re.MULTILINE)


def normalise(text: str) -> str:
    """把一页的文字压成只剩数字与小数点，好让 `17.93` 与 `17. 93` 都能命中。

    扫描件的 OCR 会在数字中间塞进空格与逗号；连字符与中点也常被读成别的东西。
    压掉分隔符不会让匹配变得没有意义——一个四位以上数字串偶然出现在错的一页
    上的机会很低，而 `--self-test` 拿一个真实的错页证明它确实会拒。
    """
    text = BOILERPLATE.sub("", text)
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


#: 容差只用于**说明**一个太短或印成分数的值大概长什么样子，从来不用来断言
#: 页面上有什么——判过一次分母比对之后，这个函数的返回值不再驱动任何
#: 通过/不通过的判断，只出现在给人看的提示文字里。
FRACTION_TOLERANCE = 1e-5


def as_clean_fraction(value: float) -> Fraction | None:
    """`value` 精确等于某个分母 <1000 的简分数时，返回那个分数；否则 None。

    仅用于提示："这个太短查不了的小数，很可能是某张表印的 `wL^2/N` 被算成
    了十进制"——帮人判断要不要去开一下渲染图、标一个 `verified_by_eye`。
    """
    frac = Fraction(value).limit_denominator(1000)
    if frac.denominator == 0:
        return None
    if abs(float(frac) - value) > FRACTION_TOLERANCE * max(abs(value), 1e-12):
        return None
    return frac


#: 一行可以自己声明"机器在这里查不出个所以然，我看着渲染出来的页面图核过
#: 了"——覆盖两种情况，理由不同，纪律相同：
#:
#:   * 源头印的是符号公式（`wL^2/12`）而不是小数，十进制字面值天生找不到；
#:   * 这份扫描件在这个确切位置的文字层本身坏掉了（NASA 手册的 Case 7，
#:     `20` 被读成字母 `T`）。
#:
#: 两者都不用分母比对去凑——见文件顶部的说明，那条路已经被自检亲手拆穿
#: 靠不住。空口声明不算数：这一行的理由必须真的写在 SOURCE.md 里，跟
#: check_layer5.py 的 L5-5/L5-7"adjudication 必须在 SOURCE.md 里找得到"
#: 是同一条纪律。
VERIFIED_BY_EYE_COLUMN = "verified_by_eye"


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
    verified_by_eye = 0
    faults: list[str] = []

    for layer in LAYERS:
        directory = data / layer
        source_notes = ((directory / "SOURCE.md").read_text(encoding="utf-8")
                        if (directory / "SOURCE.md").is_file() else "")
        for fixture in sorted(directory.glob("*.csv")) if directory.is_dir() else []:
            for row in read_rows(fixture.read_text(encoding="utf-8")):
                page = (row.get("page_pdf") or "").strip()
                source = (row.get("source") or "").strip()
                published = (row.get("published") or "").strip()
                if not page.isdigit() or not published:
                    continue

                # 人已经看着渲染图核对过——机器不再重新判断，只核对这一行
                # 声明的理由是不是真的写在 SOURCE.md 里。
                eye_key = (row.get(VERIFIED_BY_EYE_COLUMN) or "").strip()
                if eye_key:
                    if eye_key in source_notes:
                        verified_by_eye += 1
                    else:
                        faults.append(
                            f"{fixture.name}: {row.get('tag')}: "
                            f"{VERIFIED_BY_EYE_COLUMN}={eye_key!r} 但这个理由"
                            f"不在 {directory.name}/SOURCE.md 里——"
                            f"空口说核对过不算数")
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
                if any(v in flat for v in variants(published)):
                    continue
                frac = as_clean_fraction(float(published))
                faults.append(
                    f"{fixture.name}: {row.get('tag')}: 引用 {book.name} "
                    f"PDF 第 {page} 页（印刷页 {row.get('page_printed')}），"
                    f"但该页上找不到 {published!r}"
                    + (f"（它等于简分数 {frac}——源头可能印的是这个分数，"
                       f"不是小数；看渲染图核对后标 {VERIFIED_BY_EYE_COLUMN}）"
                       if frac else ""))

    print()
    print(f"{BOLD}闸门 · 引用的页上有没有那个数{OFF}")
    # `verified_by_eye` 也算"查过"——只是走的是人核对而不是机器比对这条路。
    # 少了这一条，一份全靠人工核对、一行都没让 PdfReader 打开过的 fixture
    # 会被误判成"没查到可比对的 PDF"，跳过而不是通过。
    if checked == 0 and verified_by_eye == 0 and not faults:
        print(f"  {YELLOW}−{OFF} 一行都没查到——教材 PDF 不在 "
              f"{refs}，这道闸门只有本机跑得动")
        print(f"      （另有 {skipped_no_book} 行的来源不是本机的四本书，"
              f"{too_short} 行的数字太短、出现在哪一页都不算证据，"
              f"{verified_by_eye} 行已人工核对）")
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

    print(f"  {GREEN}✓{OFF} {checked} 行的十进制字面值逐一核对，页上都有那个数")
    if verified_by_eye:
        print(f"  {YELLOW}−{OFF} {verified_by_eye} 行机器查不出所以然"
              f"（源头印的是分数，或这份扫描件在这里文字层坏了），"
              f"已看着渲染图核对，理由记在 SOURCE.md 里")
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
    """拿一个真实的错页证明它会拒，外加人工核对分支的对错样本。

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

    # 人工核对分支：声明的理由若真在 SOURCE.md 里，必须放行；
    # 声明了却是编的，必须拒收——跟 check_layer5.py 的 L5-5/L5-7 一个道理。
    good_rows = [{"page_pdf": "1", "published": "1", "source": "durka",
                 VERIFIED_BY_EYE_COLUMN: "SELFTEST-OK"}]
    bad_rows = [{"page_pdf": "1", "published": "1", "source": "durka",
                VERIFIED_BY_EYE_COLUMN: "SELFTEST-DANGLING"}]
    fake_source = "SELFTEST-OK is a made-up key that this fake SOURCE.md contains."

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / "tests" / "data" / "examples"
        tmp_path.mkdir(parents=True)
        (tmp_path / "SOURCE.md").write_text(fake_source, encoding="utf-8")
        for name, rows_, want_pass in (
            ("声明的理由真的在 SOURCE.md 里", good_rows, True),
            ("声明的理由是编的", bad_rows, False),
        ):
            (tmp_path / "probe.csv").write_text(
                "page_pdf,published,source," + VERIFIED_BY_EYE_COLUMN + "\n"
                + ",".join(rows_[0].values()) + "\n", encoding="utf-8")
            code = run(Path(tmp) / "tests" / "data", refs, PdfReader)
            passed = (code == 0)
            good = (passed == want_pass)
            ok &= good
            print(f"  {'PASS' if good else 'FAIL'}  人工核对：{name}"
                  f"（{'通过' if passed else '未通过'}）")

    print("\n自检通过——闸门确实分得出对页与错页，也分得出真理由与编的理由"
          if ok else "\n自检失败")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

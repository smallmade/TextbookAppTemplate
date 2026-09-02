#!/usr/bin/env python3
"""Gate 07 / M6 —— 理论手册的**散文源**完整、有实质内容、且被人对抗复核过。

这道闸门与 `check_manual_coverage.py` 查的不是一件事，两道都要有：

  * `check_manual_coverage.py` 查**渲染产物**——每个出货模块的 id 或 title
    在 HTML 全文里出现过。它抓的是「整节不存在」。
  * 本闸门查**散文源**——`docs/theory/*.toml` 里每个模块八个键齐全、每一段
    真的写了东西、没有占位符，并且有一份对抗复核记录。

为什么需要第二道：一个模块只要有一节标题，前一道就绿了，而那一节可以是
生成器从正典模板展开的三行套话。MechanicsOne 的理论手册**曾经整册都是**
那个样子——53 个模块小节全自动展开，20,236 字，比姊妹项目薄 3.6 倍，而
所有闸门全绿。字数不是质量，但**一段两行的推导一定不是推导**。

还有一件事在这之前没有任何机器在看：**对抗复核**。规范附录 I 要求理论手册
的撰写者与复核者是不同的代理，理由是撰写者复核自己写的东西在本系列已经出
过事。写完的人报告「我写完了」是可信的；写完的人报告「我写对了」不是。所以
本闸门要求仓库里有一份复核记录，且那份记录里**必须有误判**——一份只报命中
的复核报告，读者无从判断它的严格程度，而 100% 命中率通常意味着复核者只挑
了自己有把握的地方看。

    python tools/ci/check_theory.py [--root .] [--self-test]

退出码：0 通过 · 1 未通过 · 2 本阶段尚不适用（没有散文源目录）。
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci_config import checked, load as load_config          # noqa: E402

#: 每个模块的散文条目必须有的键。与 `build_theory.py` 的 `THEORY_FIELDS`
#: 同源；这里再列一次而不是 import 它，是**故意的重复**：闸门 import 被测
#: 生成器，就会跟着它一起错——生成器把某个键从必填改成选填时，闸门会安静
#: 地跟着放宽，而没有任何东西报出来。
REQUIRED_KEYS = ("implements", "basis", "derivation", "math",
                 "assumptions", "method", "limitations", "reading")

#: 只能是散文（字符串）的键，与只能是清单（数组）的键分开查。类型写错时
#: 生成器多半照样渲染得出东西，只是渲染成了一团，没有人会因此收到报告。
PROSE_KEYS = ("basis", "derivation", "method", "reading")
LIST_KEYS = ("implements", "math", "assumptions", "limitations")

#: 清单键里**必须非空**的那些。`math` 与 `implements` 故意不在内：一个模块
#: 可以合理地没有值得排版的展示公式，而有的画面（例如拓扑那一屏）本来就不
#: 计算任何一个内核函数拥有的东西。键必须在——「我想过了，是空的」与「我
#: 忘了写」要分得开——但内容可以是空的。
NONEMPTY_LISTS = ("assumptions", "limitations")

#: 一段推导至少要有的字数。定在 40 是因为它要能放过一句真的很短但完整的
#: 说明，同时挡住「见上」「同前一节」这类把空白说成内容的写法。
MIN_PROSE_WORDS = {"basis": 25, "derivation": 40, "method": 15, "reading": 20}

#: 占位符。中英文都收，因为本系列的散文源两种语言都出现过。
PLACEHOLDER = re.compile(
    r"\b(TODO|TBD|FIXME|XXX|PLACEHOLDER|LOREM IPSUM)\b|待补|待写|占位|此处从略",
    re.IGNORECASE)


def shipping_modules(spec: dict) -> list[dict]:
    """出货清单。优先读 `meta.ships_in_v1`——正典自己的权威清单。

    与另外两道闸门同一份逻辑。手写的「哪些算数」清单在本系列漏过四次，所以
    凡是要回答「哪些模块算数」的地方，一律回到正典的同一个字段。
    """
    declared = (spec.get("meta") or {}).get("ships_in_v1")
    modules = spec.get("modules", [])
    if declared:
        want = set(declared)
        return [m for m in modules if m.get("id") in want]
    return [m for m in modules
            if m.get("ships_in_v1") or m.get("tier") == "core"]


def load_prose(prose_dir: Path) -> tuple[dict[str, dict], list[str]]:
    """按模块 id 收齐散文条目；同一个 id 出现在两个文件里是错误。

    不是「后写的赢」：静默覆盖会让人以为自己编辑的那一份在生效，而其实不是。
    """
    out: dict[str, dict] = {}
    seen: dict[str, str] = {}
    problems: list[str] = []
    for path in sorted(prose_dir.glob("*.toml")):
        if path.name == "front.toml":
            continue
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            problems.append(f"{path.name} 不是合法的 TOML：{exc}")
            continue
        for mid, entry in data.items():
            if not isinstance(entry, dict):
                continue
            if mid in seen:
                problems.append(
                    f"模块 {mid} 同时出现在 {seen[mid]} 与 {path.name}——"
                    "一个模块只能有一份散文源，否则你编辑的那一份可能不是"
                    "在生效的那一份")
                continue
            seen[mid] = path.name
            out[mid] = entry
    return out, problems


def words(value) -> int:
    text = " ".join(value) if isinstance(value, list) else str(value)
    return len(text.split())


def audit_entry(mid: str, entry: dict) -> list[str]:
    """一个模块的散文条目查一遍，返回问题清单（空 = 通过）。"""
    bad: list[str] = []
    for key in REQUIRED_KEYS:
        if key not in entry:
            bad.append(f"{mid}：缺键 `{key}`")
            continue
        value = entry[key]
        if key in LIST_KEYS:
            if not isinstance(value, list):
                bad.append(f"{mid}.{key} 应当是清单，实际是 "
                           f"{type(value).__name__}")
            elif not value and key in NONEMPTY_LISTS:
                bad.append(f"{mid}.{key} 是空清单——键在，内容不在")
            elif any(not str(v).strip() for v in value):
                bad.append(f"{mid}.{key} 里有空条目")
        else:
            if not isinstance(value, str):
                bad.append(f"{mid}.{key} 应当是散文，实际是 "
                           f"{type(value).__name__}")
            elif not value.strip():
                bad.append(f"{mid}.{key} 是空串")
            elif words(value) < MIN_PROSE_WORDS.get(key, 0):
                bad.append(f"{mid}.{key} 只有 {words(value)} 词"
                           f"（至少 {MIN_PROSE_WORDS[key]}）——"
                           "一段两行的推导不是推导")
    blob = json.dumps(entry, ensure_ascii=False)
    if PLACEHOLDER.search(blob):
        hit = PLACEHOLDER.search(blob).group(0)
        bad.append(f"{mid}：散文里留着占位符 `{hit}`")
    return bad


def public_names(package: Path) -> set[str]:
    """包里每一个 def / class 的名字，用**解析**而不是 import 拿到。

    与对等测试同一个理由：手写的「有什么」清单会与真的有什么分叉。解析而
    不 import，是因为这道闸门要在依赖装不全的机器上也跑得动。
    """
    names: set[str] = set()
    for source in package.rglob("*.py"):
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
                names.add(node.name)
    return names


def audit_implements(prose: dict[str, dict], names: set[str],
                     where: str) -> list[str]:
    """散文里 `implements` 点名的函数，逐个确认它今天还在。

    这一条是把散文**锚在代码上**的东西。改名一个内核函数而不改散文，手册
    就会继续描述一个已经不存在的实现——而手册是这个项目最公开的文件，也是
    唯一一份主张「结果可信」的文件。本系列已经发生过一次：一份清单声称两个
    出货功能，而它们从来没有被实现，没有任何东西抓到，因为没有任何东西在拿
    散文和代码比对。
    """
    bad: list[str] = []
    if not names:
        return bad
    for mid in sorted(prose):
        for ref in prose[mid].get("implements") or []:
            leaf = str(ref).rsplit(".", 1)[-1]
            if leaf not in names:
                bad.append(f"{mid}.implements 点名的 `{ref}` 在 {where} 里"
                           "不存在——散文脱离了代码")
    return bad


#: 复核记录里那一行机器可读的标记。
#:
#: 早一版是拿正则去读散文里的「复核了 N 个模块」，第一份真实的复核记录就没
#: 命中——它把数字排成了表格。闸门去解析散文，最后总是在追着散文的写法改，
#: 而每改一次，它能读懂的写法就窄一分。所以这里换成与 `CHECKED n=` 同一个
#: 做法：要一行固定形状的标记，散文爱怎么写怎么写。
REVIEW_MARK = re.compile(
    r"REVIEW\s+n_modules=(\d+)\s+n_raised=(\d+)\s+"
    r"n_upheld=(\d+)\s+n_false_alarm=(\d+)")

#: 提出的条数超过这个数还一条误判都没有，判未通过。
#:
#: 不是「零误判即造假」——提了三条中三条是可信的。但提了几十条而条条命中，
#: 通常说明复核者只挑了自己有把握的地方看，那正是对抗复核要防的事。
CREDIBLE_WITHOUT_FALSE_ALARM = 5


def audit_review(path: Path) -> tuple[list[str], int]:
    """对抗复核记录。返回（问题清单，复核到的模块数）。"""
    if not path.exists():
        return ([f"没有对抗复核记录 {path.name}——理论手册是这个 App 唯一"
                 "能向审稿人证明「算得对」的文件，撰写者自己说写对了不算"], 0)
    text = path.read_text(encoding="utf-8")
    bad: list[str] = []
    hit = REVIEW_MARK.search(text)
    if hit is None:
        return ([f"{path.name} 里没有那一行机器可读的标记。补一行：\n"
                 "        REVIEW n_modules=<复核了几个模块> "
                 "n_raised=<提出几条> n_upheld=<其中几条成立> "
                 "n_false_alarm=<几条是复核者自己误判>"], 0)
    modules, raised, upheld, false_alarm = (int(g) for g in hit.groups())
    if modules == 0:
        bad.append(f"{path.name}：n_modules=0——"
                   "一份没有分母的复核报告，说不清它覆盖了什么")
    if raised == 0:
        bad.append(f"{path.name}：n_raised=0——"
                   "一条疑点都没提出的复核，与没有复核不可区分")
    if upheld + false_alarm != raised:
        bad.append(f"{path.name}：{upheld} + {false_alarm} ≠ {raised}——"
                   "成立的加上误判的对不上提出的总数。这一条查的不是算术，"
                   "是这份记录到底有没有人在按条数记账")
    if false_alarm == 0 and raised > CREDIBLE_WITHOUT_FALSE_ALARM:
        bad.append(f"{path.name}：提出 {raised} 条而一条误判都没有。"
                   "一份只报命中的复核报告，读者无从判断它的严格程度——"
                   "条条命中通常说明复核者只看了自己有把握的地方")
    return bad, modules


def run(root: Path) -> int:
    cfg = load_config(root)
    spec_path = root / (getattr(cfg, "spec_path", None) or
                        "spec/specification.json")
    prose_dir = root / getattr(cfg, "theory_prose_dir", None or "docs/theory")
    if not prose_dir.is_dir() or not list(prose_dir.glob("*.toml")):
        print(f"尚不适用：没有 {prose_dir.relative_to(root)}/*.toml —— "
              "理论手册还是全自动由正典展开的，没有手写散文源可查。")
        return 2
    if not spec_path.exists():
        print(f"尚不适用：找不到正典 {spec_path}")
        return 2

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    modules = shipping_modules(spec)
    prose, problems = load_prose(prose_dir)

    missing = [m["id"] for m in modules if m["id"] not in prose]
    for mid in missing:
        problems.append(f"出货模块 {mid} 在散文源里一条也没有——"
                        "它那一节会退回成模板展开的套话")

    # 每一条散文都会被渲染进手册，所以每一条都按同一个标准查——不只是出货
    # 的那些。写给 extended 层模块的散文一样会有读者看见。
    known = {m["id"] for m in spec.get("modules", [])}
    checked_entries = 0
    for mid in sorted(prose):
        if mid not in known:
            # 正典里根本没有这个 id：它写的是谁的推导？多半是模块改名或删除
            # 之后，散文源没有跟着改——那一节会带着一个不存在的编号出货。
            problems.append(f"散文源里有正典已不存在的模块 {mid}——"
                            "它写的是谁的推导？")
            continue
        checked_entries += 1
        problems += audit_entry(mid, prose[mid])

    # `cfg.get(...)`，不是 `getattr(cfg, ...)`：Config 把配置放在 `.data` 里，
    # 没有同名属性，所以 getattr 恒为 None——ci.toml 点名的包目录被**静默
    # 忽略**，每次都回落到 python/src 或 src。它一直「能用」，因为 rglob 往下
    # 走仍然扫得到那些函数；但这正是本工具链反复点名的那种失效：一个读不到
    # 配置的闸门，和一个读到了配置的闸门，在日志里长得一模一样。
    package = None
    for candidate in (cfg.get("python_package_dir"),
                      "python/src", "src"):
        if not candidate:
            continue
        here = root / candidate
        if here.is_dir():
            package = here
            break
    if package is not None:
        problems += audit_implements(prose, public_names(package),
                                     str(package.relative_to(root)))

    review_bad, reviewed = audit_review(prose_dir / "REVIEW.md")
    problems += review_bad

    front = prose_dir / "front.toml"
    if not front.exists():
        problems.append("没有 front.toml——前言四章（范围与读法 / 记号与符号"
                        "约定 / 通用解法 / 验证方法）是理论手册与一叠公式的"
                        "区别所在")

    n = checked_entries + (1 if front.exists() else 0) + 1   # +1 = REVIEW.md
    print(checked(n, "个散文对象",
                  f"{checked_entries} 个模块条目 + 前言 + 复核记录；"
                  f"复核记录称覆盖 {reviewed} 个模块"))

    if problems:
        print(f"✗ {len(problems)} 处未通过：")
        for p in problems[:40]:
            print(f"    {p}")
        if len(problems) > 40:
            print(f"    …… 另有 {len(problems) - 40} 处")
        return 1

    total = sum(words(entry.get(k) or "")
                for entry in prose.values() for k in PROSE_KEYS)
    print(f"✓ 理论手册散文源完整：{checked_entries} 个模块条目"
          f"（含全部 {len(modules)} 个出货模块），八个键齐全、无占位符、"
          f"implements 点名的函数逐一存在，共 {total:,} 词；"
          f"对抗复核记录覆盖 {reviewed} 个模块且记下了误判")
    return 0


# --------------------------------------------------------------------------- #
# 自检 —— 没有已知会失败的样本，就没有证据说这道闸门还活着
# --------------------------------------------------------------------------- #

GOOD_ENTRY = {
    "implements": ["kernel.demo.f"],
    "basis": " ".join(["word"] * 30),
    "derivation": " ".join(["word"] * 50),
    "math": ["a=b"],
    "assumptions": ["one"],
    "method": " ".join(["word"] * 20),
    "limitations": ["one"],
    "reading": " ".join(["word"] * 25),
}

GOOD_REVIEW = ("# 复核\n\nREVIEW n_modules=20 n_raised=12 n_upheld=9 "
               "n_false_alarm=3\n\n复核了 20 个模块，误判逐条列在 §4。\n")


def self_test() -> int:
    import copy
    import tempfile

    samples: list[tuple[str, dict, str, bool]] = [
        ("放行  八个键齐全、复核记录含误判", {}, GOOD_REVIEW, True),
        ("抓到  缺一个键", {"drop": "derivation"}, GOOD_REVIEW, False),
        ("抓到  推导只有两行", {"short": "derivation"}, GOOD_REVIEW, False),
        ("抓到  清单键写成了字符串", {"scalar": "assumptions"}, GOOD_REVIEW,
         False),
        ("放行  math 为空（有的模块没有值得排版的展示公式）",
         {"empty": "math"}, GOOD_REVIEW, True),
        ("抓到  assumptions 为空", {"empty": "assumptions"}, GOOD_REVIEW,
         False),
        ("抓到  implements 点名了一个代码里没有的函数",
         {"dangling": True}, GOOD_REVIEW, False),
        ("抓到  留着占位符", {"placeholder": True}, GOOD_REVIEW, False),
        ("抓到  出货模块一条散文都没有", {"nomodule": True}, GOOD_REVIEW,
         False),
        ("放行  正典里有、但不在 v1 出货清单的模块也写了散文",
         {"extra_canon": "M02"}, GOOD_REVIEW, True),
        ("抓到  散文写给一个正典里根本没有的 id",
         {"extra_canon": None}, GOOD_REVIEW, False),
        ("抓到  根本没有复核记录", {}, None, False),
        ("抓到  复核记录没有那一行机器可读的标记", {},
         "# 复核\n\n看过了，复核了 20 个模块，有 3 条误判。\n", False),
        ("抓到  复核记录 100% 命中、一条误判都没有", {},
         "# 复核\n\nREVIEW n_modules=20 n_raised=9 n_upheld=9 "
         "n_false_alarm=0\n", False),
        ("放行  只提出 3 条、3 条全中（少量全中是可信的）", {},
         "# 复核\n\nREVIEW n_modules=20 n_raised=3 n_upheld=3 "
         "n_false_alarm=0\n", True),
        ("抓到  成立数加误判数对不上提出的总数", {},
         "# 复核\n\nREVIEW n_modules=20 n_raised=12 n_upheld=9 "
         "n_false_alarm=1\n", False),
        ("抓到  n_modules=0（没有分母）", {},
         "# 复核\n\nREVIEW n_modules=0 n_raised=12 n_upheld=9 "
         "n_false_alarm=3\n", False),
    ]

    ok = True
    print("check_theory.py 自检")
    for label, mutate, review, expect_pass in samples:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "spec").mkdir()
            (root / "docs" / "theory").mkdir(parents=True)
            pkg = root / "python" / "src" / "demokit"
            pkg.mkdir(parents=True)
            (pkg / "demo.py").write_text("def f():\n    return 1\n",
                                         encoding="utf-8")
            (root / "ci.toml").write_text('slug = "demo"\n', encoding="utf-8")
            canon_modules = [{"id": "M01", "title": "Demo"}]
            if "extra_canon" in mutate and mutate["extra_canon"]:
                canon_modules.append({"id": mutate["extra_canon"],
                                      "title": "Extended"})
            (root / "spec" / "specification.json").write_text(json.dumps(
                {"meta": {"ships_in_v1": ["M01"]},
                 "modules": canon_modules}), encoding="utf-8")

            entry = copy.deepcopy(GOOD_ENTRY)
            if "drop" in mutate:
                del entry[mutate["drop"]]
            if "short" in mutate:
                entry[mutate["short"]] = "two words"
            if "scalar" in mutate:
                entry[mutate["scalar"]] = "not a list"
            if "empty" in mutate:
                entry[mutate["empty"]] = []
            if mutate.get("placeholder"):
                entry["basis"] = entry["basis"] + " TODO"
            if mutate.get("dangling"):
                entry["implements"] = ["kernel.demo.gone_last_week"]

            body = {} if mutate.get("nomodule") else {"M01": entry}
            if "extra_canon" in mutate:
                # 两个样本共用这一支：给 M02 也写一份散文。上面的正典里有
                # M02 时应当放行，没有时应当抓到。
                body["M02"] = copy.deepcopy(GOOD_ENTRY)
            (root / "docs" / "theory" / "a.toml").write_text(
                _toml(body), encoding="utf-8")
            (root / "docs" / "theory" / "front.toml").write_text(
                'title = "front"\n', encoding="utf-8")
            if review is not None:
                (root / "docs" / "theory" / "REVIEW.md").write_text(
                    review, encoding="utf-8")

            import contextlib
            import io
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = run(root)
            passed = (code == 0)
            good = (passed == expect_pass)
            ok &= good
            print(f"  {'PASS' if good else 'FAIL'}  {label}")
            if not good:
                print("        " + buf.getvalue().replace("\n", "\n        "))

    # 空目录必须是「尚不适用」而不是「通过」——本系列吃过三次「数到零然后
    # 报绿」的亏，所以这一条单独验。
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "ci.toml").write_text('slug = "demo"\n', encoding="utf-8")
        code = run(root)
        good = (code == 2)
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  没有散文源时退 2（尚不适用），"
              "不是退 0（通过）")

    print("\n自检通过——闸门确实在工作" if ok else "\n自检失败")
    return 0 if ok else 1


def _toml(data: dict) -> str:
    """够用就好的 TOML 写出器，只给自检用。"""
    out = []
    for mid, entry in data.items():
        out.append(f"[{mid}]")
        for key, value in entry.items():
            if isinstance(value, list):
                items = ", ".join(json.dumps(v, ensure_ascii=False)
                                  for v in value)
                out.append(f"{key} = [{items}]")
            else:
                out.append(f"{key} = {json.dumps(value, ensure_ascii=False)}")
        out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    sys.exit(self_test() if args.self_test else run(args.root.resolve()))

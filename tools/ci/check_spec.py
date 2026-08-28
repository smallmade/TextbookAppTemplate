#!/usr/bin/env python3
"""Gate 01 —— 正典自检。

    python check_spec.py spec/specification.json [--shipped]

--shipped 检查的是**剥离后**的出货副本：citation 与受版权来源信息必须已经
不在里面（架构上的第一道法律隔离防线，见规范 阶段 06）。

退出码 0 = 通过。
"""

import argparse
import json
import re
import sys
from pathlib import Path

# 教材标识：出现在 formula_display 或任何出货字段里就是法律风险。
# 这张表随项目增长——每加一部教材就把作者姓氏加进来。
TEXTBOOK_MARKS = re.compile(
    r"\b(anderson|gere|hibbeler|cengel|moran|incropera|timoshenko|white|"
    r"munson|turns|law|roark)\b|"
    r"(Eq\.\s*\d|Example\s+\d|Problem\s+\d|Table\s+\d+-|§\s*\d)",
    re.IGNORECASE,
)

REQUIRED_TOP = ("meta", "sources", "meanings", "modules", "validity", "build")


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.checks = 0

    def check(self, ok: bool, msg: str) -> bool:
        self.checks += 1
        if not ok:
            self.errors.append(msg)
        return ok


def validate(spec: dict, shipped: bool) -> Report:
    r = Report()

    for key in REQUIRED_TOP:
        r.check(key in spec, f"缺顶层键 {key}")
    if r.errors:
        return r

    # —— sources ——
    sources = spec["sources"]
    r.check(len(sources) >= 2, "sources 至少两笔")
    roles = {s.get("role") for s in sources}
    r.check("independent-check" in roles,
            "sources 必须含一笔 role=independent-check —— "
            "没有第二源，五层验证的最后一层无法建立（选题闸第 6 项）")
    for i, s in enumerate(sources):
        r.check("licence" in s, f"sources[{i}] 缺 licence")
        if shipped and s.get("licence") == "copyrighted":
            r.check(not s.get("author") and not s.get("title"),
                    f"sources[{i}] 是受版权来源，出货副本里 author/title 必须已剥离")

    # —— meanings ——
    meanings = spec["meanings"]
    symbols_used: set[str] = set()
    for m in spec["modules"]:
        for field in ("entries", "outputs"):
            for item in m.get(field, []):
                sym = item.get("symbol") if isinstance(item, dict) else None
                if sym:
                    symbols_used.add(sym)
    missing = sorted(symbols_used - set(meanings))
    r.check(not missing,
            f"这些符号出现在 entries/outputs 却没有 meanings 条目：{missing}")

    # —— modules ——
    r.check(len(spec["modules"]) > 0, "modules 不能为空")
    for m in spec["modules"]:
        mid = m.get("id", "<无 id>")

        if shipped:
            r.check("citation" not in m,
                    f"module {mid}: 出货副本里 citation 必须已剥离")
        else:
            cit = m.get("citation", "")
            r.check(bool(cit) and "TODO" not in cit,
                    f"module {mid}: citation 为空或仍是 TODO")
            r.check(bool(re.search(r"\d", str(cit))),
                    f"module {mid}: citation 必须精确到式号，不是「第 5 章」")

        fd = m.get("formula_display", "")
        r.check(bool(fd) and "TODO" not in fd,
                f"module {mid}: 缺 formula_display")
        hit = TEXTBOOK_MARKS.search(str(fd))
        # 消息只在真的命中时构造：f-string 是急求值的，写在 r.check() 的实参里
        # 会在没命中（hit 为 None）时照样求值并崩掉。
        if hit:
            r.check(False,
                    f"module {mid}: formula_display 含教材标识 {hit.group(0)!r} —— "
                    f"数学关系可以显示，教材的表达不可以（阶段 06 三层规则）")
        else:
            r.check(True, "")

        has_property = bool(m.get("invariants")) or bool(m.get("trends"))
        r.check(has_property,
                f"module {mid}: 至少要有一条 invariant 或 trend —— "
                f"单点比对只能检查你想到的点，恒等式才能抓到你没想到的组合")

    # —— build.strip_on_ship ——
    if not shipped:
        strip = spec.get("build", {}).get("strip_on_ship", [])
        r.check("citation" in strip,
                "build.strip_on_ship 必须含 citation")
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("spec", type=Path)
    ap.add_argument("--shipped", action="store_true",
                    help="检查剥离后的出货副本")
    ap.add_argument("--selftest", action="store_true",
                    help="用一份已知不合格的正典自证检查确实在工作")
    args = ap.parse_args()

    if args.selftest:
        # 闸门必须能自证还活着：一份必然不合格的输入若被判通过，
        # 说明检查逻辑坏了，而「没找到问题」会被误读成「通过」。
        bad = {"meta": {}, "sources": [{"role": "primary"}],
               "meanings": {}, "modules": [{"id": "x", "citation": "第 5 章",
               "formula_display": "Gere Eq. 5-12"}],
               "validity": [], "build": {}}
        rep = validate(bad, shipped=False)
        if not rep.errors:
            print("自检失败：一份必然不合格的正典被判通过，检查逻辑不可信",
                  file=sys.stderr)
            return 2
        print(f"自检通过：不合格样本触发了 {len(rep.errors)} 条错误")
        return 0

    if not args.spec.exists():
        print(f"找不到正典：{args.spec}", file=sys.stderr)
        return 2
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"正典不是合法 JSON：{e}", file=sys.stderr)
        return 1

    rep = validate(spec, args.shipped)
    label = "出货副本" if args.shipped else "开发正典"
    if rep.errors:
        print(f"Gate 01 未通过（{label}）：{len(rep.errors)} / {rep.checks} 项")
        for e in rep.errors:
            print(f"  ✗ {e}")
        return 1
    print(f"Gate 01 通过（{label}）：{rep.checks} 项全过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

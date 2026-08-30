#!/usr/bin/env python3
"""出货正典剥离器 —— 规范 阶段 01/06 的第一道法律隔离防线。

    python strip_spec.py spec/specification.json build/specification.shipped.json

按正典自己的 build.strip_on_ship 清单剥离，然后**立刻用 check_spec.py --shipped
验一遍**。两步必须连着做：剥离脚本自己说「剥完了」不算数。

剥什么、不剥什么：

  - 每个 module 的 citation ——— 全剥。它是维护依据，不是产品内容。
  - 受版权来源的 author / title —— 剥。作者名与书名出现在商业软件里可能被
    读作背书或关联。
  - **公有领域来源的 author / title —— 不剥。** NACA / NASA / NIST 具名反而
    增强可信度且零法律风险，这是规范阶段 06 三层规则里明写的一类。

判据是来源自己的 ship 字段，不是字段名。

剥完之后还要做一件事，而且它比剥离本身重要：**把剥离前的作者姓氏当成
禁用词，回头扫一遍整份剥离后的 JSON。** 第一次跑这个脚本时，author 与
title 都剥干净了，作者姓氏却仍留在 `sources[].key` 里（`durka-1980`、
`chajes`……）—— 字段级的剥离规则天生看不见这条路径。

> 凡是「按字段名剥离」的机制，都必须再有一道**按内容**的复查，
> 否则它只在你想到的字段上有效。
"""
import json
import re
import sys
from pathlib import Path

SOURCE_FIELDS = ("author", "title", "note")


def forbidden_terms(spec: dict) -> set:
    """从开发正典派生禁用词：受版权来源的作者姓氏与完整书名。

    只取姓氏级的词元（长度 >= 4 的纯字母串），不取书名里的单词——
    「Structural」「Analysis」「Stability」是本领域的日常词汇，
    逐词禁用会让闸门乱叫，而一道会乱叫的闸门两天之内就会被关掉。
    完整书名则整串比对，不拆。
    """
    terms = set()
    for s in spec.get("sources", []):
        if s.get("ship") is True:
            continue
        for tok in re.findall(r"[A-Za-z]{4,}", s.get("author", "")):
            terms.add(tok)
        title = s.get("title", "").strip()
        if len(title) >= 8:
            terms.add(title)
    return terms


def strip(spec: dict) -> dict:
    """按 build.strip_on_ship 剥离。

    路径表达式两种形式，都要支持：

      ``key``            顶层键，或每个 module 上的同名键
      ``head[].field``   head 这个列表里每一项的 field

    **每一条规则都必须被理解。** 第一版只认三条硬编码规则（citation、
    validity[].citation、sources[].*），别的一律静默忽略——热力学项目的正典声明了
    ``provenance``、``engines[].citation``、``method_sources[].citation`` 三条，
    剥离器一条都没执行，而且什么也没说。是后面那道残留自检把它逼出来的。

    一条没人执行的剥离规则，比没有这条规则更糟：正典上写着它会被剥掉，于是
    没有人再去检查它。所以现在不认识的路径直接抛错。
    """
    out = json.loads(json.dumps(spec))          # 深拷贝，绝不就地改开发正典
    rules = list(out.get("build", {}).get("strip_on_ship", []))
    unhandled: list[str] = []

    for rule in rules:
        if rule.startswith("sources[]."):
            continue                            # 下面按许可单独处理
        if "[]." in rule:
            head, _, field = rule.partition("[].")
            container = out.get(head)
            if isinstance(container, list):
                for item in container:
                    if isinstance(item, dict):
                        item.pop(field, None)
            elif isinstance(container, dict):
                for item in container.values():
                    if isinstance(item, dict):
                        item.pop(field, None)
            elif container is not None:
                unhandled.append(rule)
            continue
        # 裸键：顶层，外加每个 module 上的同名键（citation 就是这样两处都有）
        touched = out.pop(rule, None) is not None
        for m in out.get("modules", []):
            if m.pop(rule, None) is not None:
                touched = True
        if not touched:
            unhandled.append(rule)

    for s in out.get("sources", []):
        if s.get("ship") is True:               # 公有领域：具名是资产，留着
            continue
        for f in SOURCE_FIELDS:
            if f"sources[].{f}" in rules:
                s.pop(f, None)

    if unhandled:
        raise ValueError(
            "strip_on_ship 里有剥离器无法执行的路径："
            + ", ".join(repr(r) for r in unhandled)
            + " —— 一条没人执行的剥离规则比没有这条规则更糟"
        )
    return out


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    spec = json.loads(src.read_text(encoding="utf-8"))
    out = strip(spec)

    # 闸门必须能自证还活着：剥离前后必须真的不同，且残留必须为零。
    before = json.dumps(spec, ensure_ascii=False)
    after = json.dumps(out, ensure_ascii=False)
    if before == after:
        print("自检失败：剥离前后完全相同 —— strip_on_ship 没有生效", file=sys.stderr)
        return 2
    leaked = [m["id"] for m in out.get("modules", []) if "citation" in m]
    leaked += [s.get("key", "?") for s in out.get("sources", [])
               if s.get("ship") is not True and any(f in s for f in SOURCE_FIELDS)]
    if leaked:
        print(f"自检失败：这些条目仍带受版权字段 {leaked}", file=sys.stderr)
        return 1

    # 按内容复查：禁用词从开发正典自己派生，不是手写清单。
    banned = forbidden_terms(spec)
    hits = sorted({t for t in banned if t.lower() in after.lower()})
    if hits:
        print(f"自检失败：剥离后的副本里仍能搜到受版权来源的标识 {hits}", file=sys.stderr)
        print("        （字段剥干净不等于内容剥干净 —— 检查 sources[].key、"
              "module id、任何自由文本）", file=sys.stderr)
        return 1

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    kept = [s.get("title", "?") for s in out.get("sources", []) if s.get("ship") is True]
    print(f"剥离完成 → {dst}")
    print(f"  citation 已剥离：{len(spec.get('modules', []))} 个 module")
    print(f"  具名保留的公有领域来源：{len(kept)} 笔")
    print("下一步（不许跳过）：check_spec.py --shipped 验这份剥离后的副本")
    return 0


if __name__ == "__main__":
    sys.exit(main())

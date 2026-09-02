#!/usr/bin/env python3
"""Gate 01+ —— 正典的 `function:` 指针必须指到真实存在的实现。

    python check_canon_functions.py spec/specification.json --python python/src

正典是核心、界面、手册、测试四者的共同上游。`function:` 是这条上游唯一
可执行的部分：阶段 06 的界面靠它知道该调什么，阶段 07 的理论手册靠它把
公式和实现对上。**在这个闸门存在之前，它是装饰品**——正典先写、实现后写，
两边的命名各自演化，没有任何东西在看。第一次检查时 238 个引用里有 137 个
指向不存在的东西。

它抓的是第三种「没有人写的 fixture，比较的是零」：前两次是 Python 有而
Swift 没有；这一次是**正典要求、而 Python 根本没实现**——
`kernel.transform.absolute_max_shear_strain` 是 M34 的输出，Python 侧不存在，
于是没有 fixture、没有性质测试，对等测试也看不见它（Python 侧没有东西可找）。

引用语法：从**本项目的包**起逐段 getattr（`--package`，缺省由 `--python`
下唯一的包目录推断——写死包名会让这个闸门在第二个项目上整片飘红，而一个
会乱叫的闸门两天之内就会被关掉）。函数、类、方法、数据类字段
一视同仁，所以 `composition.beam.Beam.moment_at` 与
`composition.section.Properties.area` 都是合法引用。

模块可以声明 `"implemented": false` 表示【本版不实现】。这不是豁免——
数量会被打印出来，且必须与不做清单一致。
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci_config import load as load_config          # noqa: E402


def references(node: object, out: set[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "function" and isinstance(value, str):
                out.add(value)
            else:
                references(value, out)
    elif isinstance(node, list):
        for value in node:
            references(value, out)


_MISSING = object()


def _reach(obj: object, attr: str) -> object:
    """getattr，外加 dataclass 字段。

    `hasattr` 看不见**没有类级缺省值的 dataclass 字段**——而结果类型的字段
    恰恰几乎都没有缺省值。这个闸门原本因此把 `Cycle.performance` 判为不存在，
    逼着正典把指针从字段挪开，指向别的东西。本文件开头写的是「数据类字段
    一视同仁」，那句话在这个函数存在之前并不成立。
    """
    if hasattr(obj, attr):
        return getattr(obj, attr)
    fields = getattr(obj, "__dataclass_fields__", None)
    if fields is not None and attr in fields:
        return fields[attr]
    return _MISSING


#: 正典把引用写成**模块相对**的形式——`section.area_polygon`，不是
#: `kernel.section.area_polygon`。写成相对的是对的：读正典的人关心的是
#: 「哪个关系式」，不是它住在哪一层，而层的划分是实现的事。
#:
#: 代价是解析器必须知道去哪几层找。原先它只试 `<包>.<引用>`，于是**每一条
#: 引用都解析失败**——`structurekit.section` 不存在，真身是
#: `structurekit.kernel.section`。整片红的闸门等于没有闸门，而这一道还从来
#: 没在 CI 里跑过，所以没有人看见它在红。
LAYERS = ("", "kernel", "composition", "solve", "dimension", "ui")


def resolve(ref: str, package: str) -> tuple[bool, str]:
    """逐段 getattr。先试最长的模块前缀，再把余下的段当属性取。

    模块前缀在包根与各层之间搜索，因为正典的引用是模块相对的。
    """
    parts = ref.split(".")
    tried: list[str] = []
    for layer in LAYERS:
        root = f"{package}.{layer}" if layer else package
        for cut in range(len(parts), 0, -1):
            module_path = root + "." + ".".join(parts[:cut])
            try:
                obj = importlib.import_module(module_path)
            except ImportError:
                continue
            for attr in parts[cut:]:
                found = _reach(obj, attr)
                if found is _MISSING:
                    return False, f"{module_path} 里没有 {attr}"
                obj = found
            return True, ""
        tried.append(root)
    return False, f"没有可导入的模块前缀（试过 {', '.join(tried)}）"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("canon", type=Path)
    # 缺省值读 ci.toml 的 python_src_dir。写死 "python/src" 是 MechanicsOne
    # 的形状；共用工具链里写死任何一款的形状，其余几款就会在「找不到东西」
    # 与「查过了没问题」之间无声地滑向后者。命令行仍然优先。
    ap.add_argument("--python", type=Path, default=None)
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--package", default=None,
                    help="根包名；缺省由 --python 下唯一的包目录推断")
    args = ap.parse_args()
    if args.python is None:
        cfg = load_config(args.root.resolve())
        args.python = cfg.path("python_src_dir") or (args.root / "python/src")
    if not args.python.is_dir():
        print(f"尚不适用：找不到 Python 源目录 {args.python}"
              f"（ci.toml 的 python_src_dir 可以点名它）", file=sys.stderr)
        return 2
    sys.path.insert(0, str(args.python.resolve()))

    package = args.package
    if package is None:
        candidates = sorted(
            d.name for d in args.python.iterdir()
            if d.is_dir() and (d / "__init__.py").exists())
        if len(candidates) != 1:
            print(f"无法推断包名，{args.python} 下有 {candidates}；请用 --package",
                  file=sys.stderr)
            return 2
        package = candidates[0]

    canon = json.loads(args.canon.read_text(encoding="utf-8"))
    broken: dict[str, list[tuple[str, str]]] = defaultdict(list)
    deferred: list[str] = []
    total = 0
    unpointed = 0

    for module in canon["modules"]:
        refs: set[str] = set()
        references(module, refs)
        if module.get("implemented") is False:
            deferred.append(f"{module['id']} [{module.get('tier')}] {module['title']} —— {len(refs)} 个引用")
            continue
        for ref in sorted(refs):
            if not ref.strip():
                # A declared-empty pointer is a **state**, not a gap:
                # `model.py` says an output with no function is one the
                # presentation layer assembles from others.  Counted and
                # printed rather than skipped silently, because "most outputs
                # declare nothing" is worth knowing even though it is legal.
                unpointed += 1
                continue
            total += 1
            ok, why = resolve(ref, package)
            if not ok:
                broken[module["id"]].append((ref, why))

    if deferred:
        # 「没有静默上限」：本版不实现的模块必须看得见，否则它们会伪装成通过。
        print(f"· {len(deferred)} 个模块声明本版不实现，其引用不检查：")
        for line in deferred:
            print(f"    {line}")

    if broken:
        count = sum(len(v) for v in broken.values())
        print(f"✗ {count} / {total} 个 function 引用指向不存在的实现：")
        for mid in sorted(broken):
            print(f"  {mid}")
            for ref, why in broken[mid]:
                print(f"      {ref}  —— {why}")
        print("\n  正典要么描述真实存在的东西，要么明写 \"implemented\": false。")
        print("  指向空处的引用，会让阶段 06 的界面与阶段 07 的手册建立在一张错的地图上。")
        return 1

    print(f"✓ 正典的 {total} 个 function 引用全部解析成功")
    return 0


if __name__ == "__main__":
    sys.exit(main())

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


def resolve(ref: str, package: str) -> tuple[bool, str]:
    """逐段 getattr。先试最长的模块前缀，再把余下的段当属性取。"""
    parts = ref.split(".")
    for cut in range(len(parts), 0, -1):
        module_path = package + "." + ".".join(parts[:cut])
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
    return False, f"没有可导入的模块前缀（试到 {package}.{parts[0]}）"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("canon", type=Path)
    ap.add_argument("--python", type=Path, default=Path("python/src"))
    ap.add_argument("--package", default=None,
                    help="根包名；缺省由 --python 下唯一的包目录推断")
    args = ap.parse_args()
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

    for module in canon["modules"]:
        refs: set[str] = set()
        references(module, refs)
        if module.get("implemented") is False:
            deferred.append(f"{module['id']} [{module.get('tier')}] {module['title']} —— {len(refs)} 个引用")
            continue
        for ref in sorted(refs):
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

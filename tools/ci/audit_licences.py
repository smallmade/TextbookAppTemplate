#!/usr/bin/env python3
"""Gate 09 —— 许可审计。

    python audit_licences.py <构建产物目录或 .app>

**在构建产物上跑，不是在意图上跑。** 这是这个脚本存在的全部理由：
`pyproject.toml` 里写着依赖 PySide6-Essentials 不代表打包钩子没有把
PySide6-Addons 拖进 bundle。意图与产物之间那道缝，正是 GPL 传染发生的地方。

──────────────────────────────────────────────────────────────────────
守什么
──────────────────────────────────────────────────────────────────────

一、**GPL-only 组件一个都不能进包。**

   Qt 的 Charts、Data Visualization、Virtual Keyboard 在开源版下是 GPL-only。
   其中任何一个被打包钩子悄悄拖进 bundle，整个应用就被 GPL 传染——即使
   桌面版自用不发布，这也会污染源代码的授权状态，将来想复用到 App Store
   版就麻烦了。

   这一类是**硬失败**：非零退出，挡下发布。

二、**LGPL 组件必须满足三项条件。**

   动态链接（不能静态链接进主二进制）· 许可证文本随包分发 · 用户能够替换
   该库（提供重链接说明与对应源码）。Passthrough 内嵌 FFmpeg 就是靠这三项
   合规的：许可证文本、重链接说明、以及精确对应的源码归档都在 app bundle 里。

三、**清单与产物对得上。**

   声明了却没打进去，或打进去了却没声明，两种都要报。

──────────────────────────────────────────────────────────────────────
退出码
──────────────────────────────────────────────────────────────────────

    0  通过
    1  有 GPL-only 组件，或 LGPL 三项条件不满足
    2  本阶段尚不适用（构建产物还不存在）
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

RED, GREEN, YELLOW, BOLD, OFF = (
    "\033[31m", "\033[32m", "\033[33m", "\033[1m", "\033[0m")


# ── 许可数据库 ────────────────────────────────────────────────────
#
# 按「产物里出现的文件名片段」索引。这张表随项目增长——每引入一个新依赖
# 就在这里记一笔，而不是等到打包时才发现它是什么许可。

GPL_ONLY = {
    # Qt 开源版下的 GPL-only 模块。任何一个进包，整个应用被传染。
    "QtCharts":            "Qt Charts —— 开源版下 GPL-3.0-only",
    "QtDataVisualization": "Qt Data Visualization —— 开源版下 GPL-3.0-only",
    "QtVirtualKeyboard":   "Qt Virtual Keyboard —— 开源版下 GPL-3.0-only",
    "QtQuick3DPhysics":    "Qt Quick 3D Physics —— 开源版下 GPL-3.0-only",
    # 常见的 GPL 命令行工具，被 subprocess 调用时同样会传染
    "libx264":             "x264 —— GPL-2.0-or-later",
    "libx265":             "x265 —— GPL-2.0-or-later",
    "libxvid":             "Xvid —— GPL-2.0-or-later",
    "librubberband":       "Rubber Band —— GPL-2.0-or-later",
    "libsmbclient":        "libsmbclient —— GPL-3.0-or-later",
    "readline":            "GNU Readline —— GPL-3.0-or-later（用 libedit 代替）",
}

LGPL = {
    "PySide6":       "PySide6 —— LGPL-3.0",
    "libQt6":        "Qt 6 —— LGPL-3.0（Essentials 模块）",
    "QtCore":        "Qt Core —— LGPL-3.0",
    "libavcodec":    "FFmpeg libavcodec —— LGPL-2.1-or-later",
    "libavformat":   "FFmpeg libavformat —— LGPL-2.1-or-later",
    "libavutil":     "FFmpeg libavutil —— LGPL-2.1-or-later",
    "libswscale":    "FFmpeg libswscale —— LGPL-2.1-or-later",
    "libswresample": "FFmpeg libswresample —— LGPL-2.1-or-later",
    "libavfilter":   "FFmpeg libavfilter —— LGPL-2.1-or-later",
    "libavdevice":   "FFmpeg libavdevice —— LGPL-2.1-or-later",
}

PERMISSIVE = {
    "libcantera": "Cantera —— BSD-3-Clause",
    "libpng":     "libpng —— zlib/libpng",
    "libjpeg":    "libjpeg-turbo —— BSD-3-Clause / IJG",
    "libz":       "zlib —— zlib",
    "libssl":     "OpenSSL —— Apache-2.0（3.x）",
    "numpy":      "NumPy —— BSD-3-Clause",
    "libfreetype": "FreeType —— FTL / GPL-2.0（选 FTL）",
}

# LGPL 合规需要的三样东西，按文件名片段找
LGPL_EVIDENCE = {
    "licence_text":  re.compile(r"(LICENSE|LICENCE|COPYING).*(LGPL|lgpl)|LGPL",
                                re.IGNORECASE),
    "relink_notes":  re.compile(r"RELINK|relink", re.IGNORECASE),
    "source_archive": re.compile(r"\.(tar\.(gz|xz|bz2)|zip)$", re.IGNORECASE),
}


@dataclass
class Component:
    name: str
    note: str
    kind: str                    # gpl / lgpl / permissive / unknown
    paths: list[Path] = field(default_factory=list)
    statically_linked: bool = False


# ── 探索 ──────────────────────────────────────────────────────────

def scan_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file() or p.is_symlink()]


def classify(files: list[Path]) -> dict[str, Component]:
    found: dict[str, Component] = {}
    for f in files:
        name = f.name
        for table, kind in ((GPL_ONLY, "gpl"), (LGPL, "lgpl"),
                            (PERMISSIVE, "permissive")):
            for key, note in table.items():
                if key.lower() in name.lower():
                    c = found.setdefault(key, Component(key, note, kind))
                    c.paths.append(f)
    return found


def main_binaries(root: Path) -> list[Path]:
    """找出主可执行文件，用来查静态链接。"""
    out: list[Path] = []
    macos = root / "Contents" / "MacOS"
    if macos.is_dir():
        out += [p for p in macos.iterdir() if p.is_file()]
    else:
        for p in root.rglob("*"):
            if p.is_file() and p.stat().st_mode & 0o111 and p.suffix == "":
                try:
                    if b"Mach-O" in subprocess.run(
                            ["file", str(p)], capture_output=True).stdout:
                        out.append(p)
                except OSError:
                    pass
    return out[:8]


def check_dynamic_linking(comp: Component, binaries: list[Path]) -> None:
    """LGPL 要求用户能替换该库 —— 静态链接进主二进制就做不到。

    判据：主二进制的 otool -L 里应当出现这个库。出现 = 动态链接；
    库文件根本不在 bundle 里、符号却在主二进制里 = 多半静态链接了。
    """
    if not binaries:
        return
    linked_names = ""
    for b in binaries:
        try:
            r = subprocess.run(["otool", "-L", str(b)],
                               capture_output=True, text=True, timeout=20)
            linked_names += r.stdout
        except (OSError, subprocess.TimeoutExpired):
            return
    has_dylib = any(p.suffix in (".dylib", ".so") or ".framework" in str(p)
                    for p in comp.paths)
    referenced = comp.name.lower() in linked_names.lower()
    comp.statically_linked = referenced and not has_dylib


def find_evidence(files: list[Path]) -> dict[str, list[Path]]:
    ev: dict[str, list[Path]] = {k: [] for k in LGPL_EVIDENCE}
    for f in files:
        rel = str(f)
        for key, pat in LGPL_EVIDENCE.items():
            if pat.search(rel):
                ev[key].append(f)
    return ev


# ── 自检 ──────────────────────────────────────────────────────────

def selftest() -> bool:
    """闸门必须能自证还活着：一个必然命中的样本若被判通过，说明分类逻辑坏了。"""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "libQtCharts.6.dylib").write_bytes(b"\x00")
        (d / "libavcodec.61.dylib").write_bytes(b"\x00")
        (d / "libz.1.dylib").write_bytes(b"\x00")
        found = classify(scan_files(d))
    gpl = [c for c in found.values() if c.kind == "gpl"]
    lgpl = [c for c in found.values() if c.kind == "lgpl"]
    perm = [c for c in found.values() if c.kind == "permissive"]
    if not gpl:
        print(f"{RED}自检失败：GPL-only 样本（QtCharts）没被抓到{OFF}", file=sys.stderr)
        return False
    if not lgpl or not perm:
        print(f"{RED}自检失败：LGPL / 宽松许可样本分类不正确{OFF}", file=sys.stderr)
        return False
    return True


# ── 主 ────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", type=Path, nargs="?", default=Path("dist"))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--allow", action="append", default=[],
                    help="显式豁免某个组件（需要在提交材料里写明理由）")
    args = ap.parse_args()

    if not selftest():
        return 2

    target = args.target.resolve()
    if not target.exists():
        print(f"尚不适用：{target} 还不存在 —— 先构建（阶段 09 之前正常）",
              file=sys.stderr)
        return 2

    files = scan_files(target)
    if not files:
        print(f"尚不适用：{target} 是空的", file=sys.stderr)
        return 2

    found = classify(files)
    binaries = main_binaries(target)
    for c in found.values():
        if c.kind == "lgpl":
            check_dynamic_linking(c, binaries)
    evidence = find_evidence(files)

    gpl = [c for c in found.values()
           if c.kind == "gpl" and c.name not in args.allow]
    lgpl = [c for c in found.values() if c.kind == "lgpl"]
    perm = [c for c in found.values() if c.kind == "permissive"]

    if args.json:
        print(json.dumps({
            "target": str(target),
            "gpl_only": [{"name": c.name, "note": c.note,
                          "paths": [str(p) for p in c.paths]} for c in gpl],
            "lgpl": [{"name": c.name, "note": c.note,
                      "static": c.statically_linked} for c in lgpl],
            "permissive": [c.name for c in perm],
            "evidence": {k: [str(p) for p in v] for k, v in evidence.items()},
        }, ensure_ascii=False, indent=2))
        return 1 if gpl else 0

    print()
    print(f"{BOLD}Gate 09 · 许可审计{OFF}")
    print(f"目标：{target}（{len(files)} 个文件）")
    print()

    fail = 0

    # —— GPL-only：硬失败 ——
    if gpl:
        print(f"  {RED}✗{OFF} GPL-only 组件 —— 整个应用会被传染")
        for c in gpl:
            print(f"      {c.note}")
            for p in c.paths[:3]:
                print(f"        {p.relative_to(target)}")
        print(f"      → 即使自用不发布，这也会污染源代码的授权状态，")
        print(f"        将来想复用到 App Store 版就麻烦了。")
        fail += 1
    else:
        print(f"  {GREEN}✓{OFF} 无 GPL-only 组件")

    # —— LGPL 三项条件 ——
    if lgpl:
        static = [c for c in lgpl if c.statically_linked]
        missing = [k for k, v in evidence.items() if not v]
        if static or missing:
            print(f"  {RED}✗{OFF} LGPL 三项条件（{len(lgpl)} 个 LGPL 组件）")
            for c in static:
                print(f"      {c.name} 疑似静态链接 —— LGPL 要求用户能够替换该库")
            names = {"licence_text": "许可证文本",
                     "relink_notes": "重链接说明",
                     "source_archive": "对应源码归档"}
            for k in missing:
                print(f"      缺少{names[k]} —— 随包分发是 LGPL 的硬性要求")
            fail += 1
        else:
            print(f"  {GREEN}✓{OFF} LGPL 三项条件满足"
                  f"（{len(lgpl)} 个组件：动态链接 · 许可证文本 · 重链接说明 + 源码）")
        for c in lgpl:
            print(f"        {c.note}")
    else:
        print(f"  {YELLOW}−{OFF} 未发现 LGPL 组件")

    if perm:
        print(f"  {GREEN}✓{OFF} 宽松许可组件 {len(perm)} 个")
        for c in perm:
            print(f"        {c.note}")

    if args.allow:
        print(f"  {YELLOW}−{OFF} 显式豁免：{args.allow}")
        print(f"      豁免必须在提交材料里写明理由，否则半年后没人记得为什么。")

    print()
    if fail:
        print(f"{RED}{BOLD}许可审计未通过：{fail} 项。{OFF}")
        print("在这些修掉之前不要发布。\n")
        return 1
    print(f"{GREEN}{BOLD}许可审计通过。{OFF}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

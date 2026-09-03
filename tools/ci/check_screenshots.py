#!/usr/bin/env python3
"""Gate 07 —— 截图尺寸校验（ASC 实测值，不是文档值）。

    python check_screenshots.py submission/screenshots/

ASC 的 iPhone 上传框实测只收 6.5 英寸规格；6.9 英寸的 1320x2868 被当场
拒收（Passthrough 实测）。母版照常用最新模拟器抓，交付前等比缩放居中裁。

不依赖任何第三方库——直接读 PNG 头。核心零依赖的纪律，工具链也守。
（`ci_config` 是同目录的兄弟，只用标准库，不算第三方。）

**这道闸门自己犯过失效模式 2**：`rglob("*.png")` 一个都没捞到时，`count`
停在 0、`errors` 是空的，于是它印一行绿色的「通过：0 张」然后退 0——一个
空目录、或者一个名字写错的目录，看起来和十张尺寸全对的截图一模一样。而它
又没印 `CHECKED n=`，runner 的零对象闸门（不变量 6）也接不住。

> 「没有东西可查」不是「查过了是干净的」。

所以现在：印一行对象计数给 runner 看，且 `count == 0` 一律判未通过。
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci_config import checked          # noqa: E402

ACCEPTED = {
    "iphone": {(1284, 2778), (2778, 1284), (1242, 2688), (2688, 1242)},
    "ipad":   {(2064, 2752), (2752, 2064), (2048, 2732), (2732, 2048)},
    "mac":    {(1280, 800), (1440, 900), (2560, 1600), (2880, 1800)},
}
REJECTED_KNOWN = {(1320, 2868): "6.9 英寸规格，ASC 上传框实测当场拒收"}


def png_size(path: Path) -> tuple[int, int] | None:
    with path.open("rb") as fh:
        if fh.read(8) != b"\x89PNG\r\n\x1a\n":
            return None
        fh.read(4)
        if fh.read(4) != b"IHDR":
            return None
        return struct.unpack(">II", fh.read(8))


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python check_screenshots.py <screenshots 目录>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1])
    if not root.is_dir():
        print(f"找不到目录：{root}", file=sys.stderr)
        return 2

    errors, count = [], 0
    for png in sorted(root.rglob("*.png")):
        size = png_size(png)
        if size is None:
            errors.append(f"{png.name}: 不是合法 PNG")
            continue
        count += 1
        rel = png.relative_to(root)
        family = next((k for k in ACCEPTED if k in str(rel).lower()), None)
        if family is None:
            print(f"  − {rel}  {size[0]}x{size[1]}  （目录名未标明设备族，跳过）")
            continue
        if size in ACCEPTED[family]:
            print(f"  ✓ {rel}  {size[0]}x{size[1]}")
        else:
            why = REJECTED_KNOWN.get(size, "不在 ASC 实测接受的尺寸内")
            errors.append(f"{rel}: {size[0]}x{size[1]} —— {why}")

    print()
    print(checked(count, "张截图", f"扫的是 {root}"))

    if errors:
        print()
        for e in errors:
            print(f"  ✗ {e}")
        print(f"\n  接受的尺寸：iPhone 1284x2778 · iPad 13\" 2064x2752")
    if not count:
        print()
        print("  ✗ 一张合法 PNG 都没有——报「通过」等于报「没检查」")
        print(f"      扫的是 {root}")
        print("      最常见的成因是路径或目录名写错，截图其实在别处；其次是")
        print("      截图作业还没做。两种都不是「查过了是干净的」，都不该放行。")
    if errors or not count:
        return 1

    print(f"\n✓ 截图尺寸通过：{count} 张")
    return 0


if __name__ == "__main__":
    sys.exit(main())

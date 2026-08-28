#!/usr/bin/env python3
"""Gate 07 —— 商店文案字数校验。

    python check_listing_limits.py submission/LISTING.md

TexOne 的副标题曾以 36 字符被 ASC 实测拦下。入套件前机器校验，比在 ASC
表单里被拒便宜得多。

同时检查命名两条硬规则：关键词开头品牌收尾（提示，不阻塞）、
不含 Apple 商标词（阻塞——「Plot4Mac」就是这样被 GL 5.2.5 拒的）。
"""

import re
import sys
from pathlib import Path

LIMITS = {"App Name": 30, "Subtitle": 30,
          "Promotional Text": 170, "Keywords": 100, "Description": 4000}
APPLE_MARKS = ("mac", "iphone", "ipad", "ios", "macos", "ipados",
               "apple", "watch", "vision", "airplay", "retina")


def sections(text: str) -> dict[str, str]:
    """抓 `## <字段名>…` 标题下的第一个 ``` 代码块。"""
    out = {}
    for field in LIMITS:
        m = re.search(rf"^##\s*{re.escape(field)}.*?```\s*\n(.*?)```",
                      text, re.MULTILINE | re.DOTALL | re.IGNORECASE)
        if m:
            out[field] = m.group(1).strip()
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python check_listing_limits.py <LISTING.md>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"找不到：{path}", file=sys.stderr)
        return 2

    found = sections(path.read_text(encoding="utf-8"))
    errors, warnings = [], []

    for field, limit in LIMITS.items():
        if field not in found:
            warnings.append(f"没找到 {field} 段落")
            continue
        value, n = found[field], len(found[field])
        if "TODO" in value:
            warnings.append(f"{field} 仍是 TODO")
            continue
        status = "✓" if n <= limit else "✗"
        print(f"  {status} {field:<18} {n:>5} / {limit}")
        if n > limit:
            errors.append(f"{field} 超出 {n - limit} 字符")

    for field in ("App Name", "Subtitle"):
        v = found.get(field, "")
        if "TODO" in v or not v:
            continue
        hits = [m for m in APPLE_MARKS if re.search(rf"\b{m}", v.lower())]
        if hits:
            errors.append(f"{field} 含 Apple 商标词 {hits} —— Guideline 5.2.5 会拒")

    for w in warnings:
        print(f"  − {w}")

    # 全是 TODO = 尚未撰写，不是「通过」。
    # 一道在内容还没写时就报「通过」的闸门，就是静默放行——它会让人以为
    # 这一项已经查过了。用独立退出码 2 表示「本阶段尚不适用」，由 run_all
    # 判为跳过。
    # 判据是【全部】字段都写完才判通过，不是「有一个写了就算」。
    # 生成器会把 App Name 填好，若按「有一个就算」判，一份 Subtitle、
    # Keywords、Description 全是 TODO 的文案会被报成「通过」。
    unwritten = [f for f in LIMITS
                 if f not in found or "TODO" in found[f]]
    if unwritten:
        print(f"\n  − 尚未撰写完成：{unwritten} —— 本阶段尚不适用，不是通过")
        return 2

    if errors:
        print()
        for e in errors:
            print(f"  ✗ {e}")
        return 1
    print("\n✓ 文案字数与命名规则通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

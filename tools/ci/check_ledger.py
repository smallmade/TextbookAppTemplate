#!/usr/bin/env python3
"""Gate 08 —— 构建号台账与成品的 CFBundleVersion 必须对得上。

规范的规则是「号只增不减，不要试图判断这次烧没烧」。这道闸门只做那条规则
的机械部分：

  B-1  台账存在，且能解析出一个 `next = N`
  B-2  台账里已记录的号，没有一个 ≥ `next`（否则 `next` 是错的）
  B-3  成品包的 `CFBundleVersion` **等于** `next`
  B-4  两个平台的成品包版本一致（同一次投递的两个包不该是两个号）

**它查不到的那一半，必须由人查**：号有没有在 ASC 那边被占用。这台机器看不见
ASC，而一道假装看得见的闸门比没有闸门更糟——所以它把这件事打印出来，
而不是沉默地算通过。

退出码：0 通过 · 1 未通过 · 2 本阶段尚不适用
"""

from __future__ import annotations

import plistlib
import re
import subprocess
import sys
from pathlib import Path

GREEN, RED, YELLOW, BOLD, OFF = (
    "\033[32m", "\033[31m", "\033[33m", "\033[1m", "\033[0m")


def bundle_version(app: Path) -> str | None:
    """`CFBundleVersion` from a built bundle, macOS or iOS layout."""
    for candidate in (app / "Contents" / "Info.plist", app / "Info.plist"):
        if candidate.is_file():
            # Through plutil first: a plist that only a lenient reader accepts
            # is the ITMS-91056 defect, and it must not pass here either.
            probe = subprocess.run(["plutil", "-lint", str(candidate)],
                                   capture_output=True, text=True)
            if probe.returncode != 0:
                return None
            with candidate.open("rb") as handle:
                return plistlib.load(handle).get("CFBundleVersion")
    return None


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    ledger = root / "tools" / "ledger" / "builds.md"
    if not ledger.is_file():
        print(f"尚不适用：还没有 {ledger.relative_to(root)}", file=sys.stderr)
        return 2

    text = ledger.read_text(encoding="utf-8")
    match = re.search(r"^\s*next\s*=\s*(\d+)\s*$", text, re.MULTILINE)
    if match is None:
        print("未通过：台账里找不到 `next = N`", file=sys.stderr)
        return 1
    nxt = int(match.group(1))

    print()
    print(f"{BOLD}Gate 08 · 构建号台账{OFF}")
    fail = 0
    print(f"  {GREEN}✓{OFF} B-1 台账可解析      next = {nxt}")

    # B-2: a number already spent cannot be the next one.
    spent = [int(n) for n in re.findall(r"^\|\s*(\d+)\s*\|", text, re.MULTILINE)]
    clash = [n for n in spent if n >= nxt]
    if clash:
        print(f"  {RED}✗{OFF} B-2 已记录的号      {clash} 已经 ≥ next={nxt}，"
              f"next 应该是 {max(spent) + 1}")
        fail += 1
    else:
        print(f"  {GREEN}✓{OFF} B-2 已记录的号      "
              f"{len(spent)} 次投递，全部 < next")

    # B-3/B-4: what is actually in the bundles about to be shipped.
    apps = sorted((root / "dist").glob("*.app")) if (root / "dist").is_dir() else []
    if not apps:
        print(f"  {YELLOW}−{OFF} B-3 成品版本        dist/ 里没有 .app，先建包")
    else:
        versions = {}
        for app in apps:
            version = bundle_version(app)
            versions[app.name] = version
            if version is None:
                print(f"  {RED}✗{OFF} B-3 {app.name}  读不出 CFBundleVersion"
                      f"（或 plutil -lint 不过）")
                fail += 1
            elif version != str(nxt):
                print(f"  {RED}✗{OFF} B-3 {app.name}  CFBundleVersion="
                      f"{version}，台账说下一个号是 {nxt}")
                fail += 1
            else:
                print(f"  {GREEN}✓{OFF} B-3 {app.name}  CFBundleVersion={version}")
        distinct = {v for v in versions.values() if v is not None}
        if len(distinct) > 1:
            print(f"  {RED}✗{OFF} B-4 两平台版本      {versions} 不一致")
            fail += 1
        elif distinct:
            print(f"  {GREEN}✓{OFF} B-4 两平台版本      两个包同为 {distinct.pop()}")

    print()
    print(f"  {YELLOW}人工{OFF} 这台机器看不见 ASC。投递前必须自己确认："
          f"TestFlight/Builds 页上 {nxt} 号没被占用。")
    print(f"  {YELLOW}人工{OFF} Gate R-1：确认账号下此刻没有别的 App 在审。")
    print()

    if fail:
        print(f"{RED}{BOLD}未通过：{fail} 项。{OFF}\n")
        return 1
    print(f"{GREEN}{BOLD}台账机械部分通过（人工两项仍待确认）。{OFF}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

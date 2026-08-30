#!/usr/bin/env python3
"""Gate 07 —— 站点自洽性。

    python tools/ci/check_site.py site --slug mechanicsone

规范要求「五个 URL 全数回 200」，而那要等部署之后。部署之前能查、也**必须**
查的是：五个文件在不在、页面之间的链接指不指向真实存在的文件、隐私页说的和
隐私清单说的是不是同一件事。

一个 404 的 Support URL 会让 ASC 直接退回；而它在本地表现为一个拼错的
相对路径——那是这里就能抓到的。
"""

from __future__ import annotations

import argparse
import plistlib
import re
import sys
from pathlib import Path

REQUIRED = ("index.html", "support.html", "privacy.html",
            "manual/index.html", "theory/index.html")

LINK = re.compile(r'href="([^"#]+)', re.I)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("site", type=Path)
    ap.add_argument("--slug", default="structuremechone")
    ap.add_argument("--manifest", type=Path,
                    default=Path("swift/App/PrivacyInfo.xcprivacy"))
    args = ap.parse_args()
    slug = args.slug

    # Take either the site directory or a project root that contains one.
    #
    # The gate was called with the project root and looked for `index.html`
    # beside `pyproject.toml`, so it reported five missing pages on a site that
    # was complete. A gate that depends on being handed exactly the right path
    # is a gate that will one day be handed the wrong one, and this one was.
    site = args.site
    if not (site / "index.html").exists() and (site / "site" / "index.html").exists():
        site = site / "site"
    print(f"  查的是 {site}")
    base = f"https://smallmade.github.io/{slug}"
    failed = False

    missing = [name for name in REQUIRED if not (site / name).exists()]
    if missing:
        print(f"✗ 缺 {len(missing)} 个必需页面：{missing}")
        failed = True
    else:
        print(f"✓ 五个必需页面齐备（含 ASC 必填的 support / privacy）")

    # 站内链接必须指向真实文件。
    broken: list[tuple[str, str]] = []
    for page in sorted(site.rglob("*.html")):
        for href in LINK.findall(page.read_text(encoding="utf-8")):
            if href.startswith("mailto:"):
                continue
            if href.startswith(base):
                rest = href[len(base):].lstrip("/") or "index.html"
                if rest.endswith("/"):
                    rest += "index.html"
                if not (site / rest).exists():
                    broken.append((str(page.relative_to(site)), href))
            elif href.startswith("http"):
                continue  # 站外链接，这里不查（离线闸门不联网）
            else:
                target = (page.parent / href).resolve()
                if target.is_dir():
                    target = target / "index.html"
                if not target.exists():
                    broken.append((str(page.relative_to(site)), href))
    if broken:
        print(f"✗ {len(broken)} 条站内链接指向不存在的文件：")
        for where, href in broken[:10]:
            print(f"    {where} → {href}")
        failed = True
    else:
        print("✓ 站内链接全部指向真实存在的文件")

    # 隐私页与隐私清单必须说同一件事。
    privacy = (site / "privacy.html").read_text(encoding="utf-8") \
        if (site / "privacy.html").exists() else ""
    if args.manifest.exists() and privacy:
        data = plistlib.loads(args.manifest.read_bytes())
        collects = bool(data.get("NSPrivacyCollectedDataTypes"))
        tracks = bool(data.get("NSPrivacyTracking"))
        claims_none = "collects no data" in privacy.lower()
        if collects or tracks:
            if claims_none:
                print("✗ 隐私页说「不收集任何数据」，而隐私清单声明了收集／追踪")
                print("  两处不一致会被视为【元数据不实】，不是排版问题。")
                failed = True
        elif not claims_none:
            print("✗ 隐私清单说不收集，而隐私页没有这么说")
            failed = True
        else:
            print("✓ 隐私页与隐私清单一致（均为：不收集、不追踪）")

    if failed:
        return 1
    print(f"\n  部署后仍须实测五个 URL 回 200：")
    for name in REQUIRED:
        pretty = name.replace("/index.html", "/").replace("index.html", "")
        print(f"    {base}/{pretty}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci_config import checked, load as load_config          # noqa: E402

REQUIRED = ("index.html", "support.html", "privacy.html",
            "manual/index.html", "theory/index.html")

LINK = re.compile(r'href="([^"#]+)', re.I)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("site", nargs="?", type=Path, default=None,
                    help="站点目录；不给就从 ci.toml 的 site_dir 读")
    ap.add_argument("--root", type=Path, default=Path("."),
                    help="项目根，用来找 ci.toml")
    # [shared] No default. This used to default to "structuremechone" -- one
    # sibling project's own slug baked into the shared template -- so any
    # other app that forgot the flag got a clean, confident, wrong report:
    # every check passed, and the five URLs printed at the end pointed at
    # StructureOne's site, not its own. Silent and plausible is worse than
    # loud and wrong; `required=True` is the fix, matching the usage example
    # in this file's own docstring.
    #
    # [M-03] Still no default, and no longer `required=True` either. argparse
    # exits 2 on a missing required argument, and the shared runner's exit-code
    # convention reads 2 as "not applicable at this stage" -- so a forgotten
    # flag printed as a calm yellow skip whose reason column was argparse's own
    # error text, on every app sharing this template. The slug now comes from
    # the project's own ci.toml when the flag is absent, and its genuine
    # absence is a failure (1), never a skip.
    ap.add_argument("--slug", default=None,
                    help="this project's own site slug; read from ci.toml when "
                         "omitted -- there is no sensible cross-project default")
    ap.add_argument("--manifest", type=Path, default=None)
    args = ap.parse_args()

    cfg = load_config(args.root)
    slug = args.slug or cfg.get("slug")
    if not slug:
        print("✗ 不知道本项目的 slug：--slug 没给，ci.toml 里也没写。",
              file=sys.stderr)
        print("  站点隔间名没有跨项目的默认值——猜一个会让末尾印出的五个 URL "
              "指向别人的站点，而本地全绿。", file=sys.stderr)
        return 1

    # Take either the site directory or a project root that contains one.
    #
    # The gate was called with the project root and looked for `index.html`
    # beside `pyproject.toml`, so it reported five missing pages on a site that
    # was complete. A gate that depends on being handed exactly the right path
    # is a gate that will one day be handed the wrong one, and this one was.
    site = args.site
    if site is None:
        site = cfg.path("site_dir") or (args.root / "site")
    if not (site / "index.html").exists() and (site / "site" / "index.html").exists():
        site = site / "site"
    if not site.is_dir():
        print(f"尚不适用：还没有站点目录 {site}（阶段 07 之前正常）", file=sys.stderr)
        return 2
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
    pages = sorted(site.rglob("*.html"))
    links = 0
    for page in pages:
        for href in LINK.findall(page.read_text(encoding="utf-8")):
            links += 1
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
    manifest = args.manifest or (args.root / "swift/App/PrivacyInfo.xcprivacy")
    if manifest.exists() and privacy:
        data = plistlib.loads(manifest.read_bytes())
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

    print(checked(len(pages), "个页面", f"{links} 条站内链接"))
    if not pages:
        print("✗ 一个页面都没扫到——这不是「站点自洽」，这是没检查。")
        return 1
    if failed:
        return 1
    print(f"\n  部署后仍须实测五个 URL 回 200：")
    for name in REQUIRED:
        pretty = name.replace("/index.html", "/").replace("index.html", "")
        print(f"    {base}/{pretty}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""取证工具链的项目形状读取器 —— `<项目根>/ci.toml` 的 `[shots]` 一节。

**这个文件存在的理由**，和 `tools/ci/ci_config.py` 存在的理由是同一个，只是
换了一处犯：`tools/shots/` 那套脚本把**某一款** App 的形状写死在源码里——

    APP_SRC="$ROOT/build/MechanicsOne.app"
    STAGE="/private/tmp/mechanicsone-device-matrix"
    PROC="MechanicsOne"
    SIMNAME="MechanicsOne-matrix-$$-…"
    swift/Sources/MechanicsOneApp/RootView.swift

于是这套工具在别的项目上**只能靠再抄一份来用**，而本系列已经为「抄一份」
付过学费：`run_all_local.sh` 写死了 `--mine "Material Mechanics Calculator"`，
热力学那一款跑起来时报的是别人那一格，自己那格根本没查——**不会红，只会
答错**。

> 两份脚本用**内容的不同**来表达**配置的不同**，正是工具链分叉的成因。

所以形状写在项目自己的 `ci.toml`，脚本读这里。

用法（shell 侧）：

    eval "$(python3 tools/shots/shots_config.py --root . --shell)"
    echo "$SHOTS_MAC_APP"

    python3 tools/shots/shots_config.py --root . --screens        # 一行一个 id
    python3 tools/shots/shots_config.py --root . --screen-titles  # 一行一个标题
    python3 tools/shots/shots_config.py --root . --tiers mac      # TSV 档位表

键的清单见 KEYS；`--describe` 印出来。自检：`--self-test`。

──────────────────────────────────────────────────────────────────────
## 画面清单有两种形状，而**猜**是不行的

  `screenspec`     —— 画面写在一个 Swift 文件里，`ScreenSpec(id:…, title:…)`。
                      MechanicsOne 是这一种。
  `canon-sections` —— 画面**由正典生成**：一张「分节 → 正典 family」的表定
                      顺序，每节里按正典自身的模块顺序取 tier==core 的模块。
                      StructureMechOne 是这一种，它的 RootView.swift 里一个
                      `ScreenSpec` 也没有。

拿 `ScreenSpec` 的正则去扫第二种，得到的是**零个画面**。而零个画面在采集
工具里必须是「未通过」，不能是「没有画面要拍，收工」——这正是本仓库反复
发生的那一类错。所以：**形状由项目声明，读不到就报错，绝不回落到猜。**
"""

from __future__ import annotations

import argparse
import re
import shlex
import sys
import tomllib
from pathlib import Path

#: 键 → 一句话说明。顺序即 `--describe` 的输出顺序。
#: 每一个被脚本用到的键都必须在这里带一句说明，否则两周之内没人读得懂。
KEYS: dict[str, str] = {
    "mac_app": "要驱动的 Mac 成品（.app），相对项目根",
    "mac_process": "System Events 里的进程名。**不一定等于 .app 的文件名**，"
                   "它是 CFBundleName/可执行文件名那一个",
    "mac_build_hint": "Mac 成品不在时印给人看的那一条命令",
    "ipad_app": "要装进模拟器的 iPad 成品（.app）",
    "ipad_build_hint": "iPad 成品不在时印给人看的那一条命令",
    "stage_prefix": "落地目录前缀：/private/tmp/<prefix>-…（不在 Drive 路径下跑签过名的包）",
    "ax_row_path": "侧栏行的辅助功能路径，`select row N of <这里>`。"
                   "SwiftUI 换版会变，所以它是配置不是常量",
    "screens_kind": "画面清单的形状：screenspec | canon-sections",
    "sections_source": "canon-sections 用：声明「分节 → 正典 family」的 Swift 源",
    "asc_size": "商店截图的目标像素尺寸，如 2560x1600",
    "asc_window": "拿到那个像素尺寸所需的窗口点数，如 [1280, 800]",
    "asc_screens": "商店截图挑哪几屏（画面 id 的清单，顺序即出图顺序）",
}

#: 顶层键（不在 [shots] 里，但取证工具也要读）。
TOP_KEYS = ("screens_source", "walkthrough_dir", "appearances")

SCREEN_SPEC = re.compile(r'ScreenSpec\(\s*id:\s*"([^"]+)"\s*,\s*title:\s*"([^"]+)"')
#: `("Statics", ["A"]),` —— canon-sections 那张表的一行。
SECTION_ROW = re.compile(r'\(\s*"([^"]+)"\s*,\s*\[([^\]]*)\]\s*\)')
FAMILY = re.compile(r'"([^"]+)"')


class ShotsConfig:
    def __init__(self, root: Path, data: dict):
        self.root = root
        self.data = data
        self.shots = data.get("shots") or {}

    # ---- 读 ----

    def get(self, key: str, default=None):
        """`[shots]` 优先，其次顶层，最后 default。"""
        if key in self.shots:
            return self.shots[key]
        if key in self.data:
            return self.data[key]
        return default

    def path(self, key: str) -> Path | None:
        value = self.get(key)
        if value in (None, ""):
            return None
        return (self.root / str(value)).resolve()

    def require(self, key: str):
        value = self.get(key)
        if value in (None, "", []):
            raise SystemExit(
                f"✗ ci.toml 没有声明 {key}（[shots] 一节）。\n"
                f"  {KEYS.get(key, '')}\n"
                f"  取证工具不猜项目的形状——猜错时它不会红，只会拍错东西。")
        return value

    # ---- 档位 ----

    def devices(self) -> tuple[list[dict], str]:
        """(档位表, 它是从哪读来的)。

        顶层 `[[devices]]` 优先，因为闸门 `check_device_matrix.py` 读的就是
        那一处——采集与闸门读两份清单，是「已填 612 格」和「闸门要 684 格」
        同时成立的那种错法。

        顶层没有时才读 `[[shots.devices]]`。**这不是等价的两个位置**：写在
        `[[shots.devices]]` 意味着这个项目的档位闸门还接不上（例如画面清单
        是 canon-sections 形状，而闸门只认 ScreenSpec），采集先跑起来、闸门
        后接。所以调用方要把「从哪读来的」印出去，不许静默。
        """
        if self.data.get("devices"):
            return list(self.data["devices"]), "ci.toml [[devices]]（闸门读的同一处）"
        if self.shots.get("devices"):
            return list(self.shots["devices"]), \
                "ci.toml [[shots.devices]]（闸门尚未接上这一项目的画面清单形状）"
        return [], "（没有任何档位）"

    def appearances(self) -> list[str]:
        return list(self.get("appearances") or [])

    # ---- 画面 ----

    def screens(self) -> list[tuple[str, str]]:
        """[(id, title), …]，**侧栏顺序**。空清单一律抛错，不返回空表。"""
        kind = self.get("screens_kind")
        if kind is None:
            # 声明缺失时不猜：两种形状扫出来的结果一个是 N 个、一个是 0 个，
            # 而 0 个会被下游当成「没有画面要拍」。
            raise SystemExit(
                "✗ ci.toml 的 [shots] 没有 screens_kind。\n"
                f"  {KEYS['screens_kind']}\n"
                "  两种形状扫同一个文件，一种得到 N 个画面，另一种得到 0 个，\n"
                "  而 0 个在采集工具里长得像「没有画面要拍」。所以必须明写。")
        if kind == "screenspec":
            pairs = self._screens_from_screenspec()
        elif kind == "canon-sections":
            pairs = self._screens_from_canon()
        else:
            raise SystemExit(f"✗ 不认识的 screens_kind：{kind}"
                             f"（只有 screenspec / canon-sections）")
        if not pairs:
            raise SystemExit(
                f"✗ screens_kind={kind}，但一个画面都没解析出来。\n"
                "  零个画面不是通过——先把 ci.toml 的 screens_source /"
                " sections_source 修好。")
        return pairs

    def _screens_from_screenspec(self) -> list[tuple[str, str]]:
        source = self.path("screens_source")
        if source is None or not source.is_file():
            raise SystemExit(f"✗ 找不到 screens_source：{source}")
        return SCREEN_SPEC.findall(
            source.read_text(encoding="utf-8", errors="ignore"))

    def _screens_from_canon(self) -> list[tuple[str, str]]:
        """分节表定顺序，正典定内容。

        两份真身各管一半，谁也不抄谁：换一个模块只动正典，换一次分节只动那张
        表。手抄一份画面清单进 ci.toml 是本系列已经犯过的错——每一份手写的
        「哪些算数」都掉过东西。
        """
        import json
        sections_src = self.path("sections_source")
        if sections_src is None or not sections_src.is_file():
            raise SystemExit(
                f"✗ screens_kind=canon-sections，但找不到 sections_source："
                f"{sections_src}")
        canon_path = self.path("canon") or (self.root / "spec/specification.json")
        if not canon_path.is_file():
            raise SystemExit(f"✗ 找不到正典：{canon_path}")

        text = sections_src.read_text(encoding="utf-8", errors="ignore")
        # 只取 `sections` 那张表：它是文件里唯一一处 `("名字", ["A", …])` 的
        # 序列，但仍然限定在 `sections` 的方括号里，免得日后多一张同形状的表。
        block = re.search(r'sections\s*:\s*\[\(String,\s*\[String\]\)\]\s*=\s*\[(.*?)\n\s*\]',
                          text, re.S)
        if block is None:
            raise SystemExit(
                f"✗ 在 {sections_src.name} 里找不到 sections 表。\n"
                "  它的写法可能变了。零个分节不是通过。")
        sections = [(name, FAMILY.findall(families))
                    for name, families in SECTION_ROW.findall(block.group(1))]
        if not sections:
            raise SystemExit(f"✗ {sections_src.name} 的 sections 表解析出零行。")

        spec = json.loads(canon_path.read_text(encoding="utf-8"))
        modules = spec.get("modules") or []
        out: list[tuple[str, str]] = []
        for _name, families in sections:
            for module in modules:
                if module.get("family") not in families:
                    continue
                if module.get("tier") != "core":       # 只有 core 出货
                    continue
                out.append((module["id"], module.get("title", module["id"])))
        return out

    # ---- 说明 ----

    def describe(self) -> str:
        devices, where = self.devices()
        lines = [f"取证工具的项目形状 · {self.root}",
                 f"  档位来源           {where}（{len(devices)} 档）"]
        for key, why in KEYS.items():
            value = self.get(key)
            if value is None:
                lines.append(f"  {key:<18} —— 未声明（{why}）")
            else:
                lines.append(f"  {key:<18} {value!r}")
        for key in TOP_KEYS:
            lines.append(f"  {key:<18} {self.data.get(key)!r}   ← 顶层键")
        try:
            pairs = self.screens()
            lines.append(f"  画面               {len(pairs)} 屏，"
                         f"首屏 {pairs[0][0]}「{pairs[0][1]}」")
        except SystemExit as exc:
            lines.append(f"  画面               {exc}")
        return "\n".join(lines)


def load(root: Path | str = ".") -> ShotsConfig:
    root = Path(root).resolve()
    path = root / "ci.toml"
    if not path.is_file():
        raise SystemExit(f"✗ 找不到 {path}。取证工具的形状全部读它。")
    return ShotsConfig(root, tomllib.loads(path.read_text(encoding="utf-8")))


def emit_shell(cfg: ShotsConfig) -> str:
    """`eval` 得进 bash 的赋值行。前缀 SHOTS_，列表用空格连接。"""
    lines = []
    for key in KEYS:
        value = cfg.get(key)
        if value is None:
            rendered = ""
        elif isinstance(value, (list, tuple)):
            rendered = " ".join(str(v) for v in value)
        else:
            rendered = str(value)
        lines.append(f"SHOTS_{key.upper()}={shlex.quote(rendered)}")
    devices, where = cfg.devices()
    lines.append(f"SHOTS_DEVICES_FROM={shlex.quote(where)}")
    lines.append(f"SHOTS_APPEARANCES={shlex.quote(' '.join(cfg.appearances()))}")
    return "\n".join(lines)


def tiers_tsv(cfg: ShotsConfig, want: str) -> str:
    """name<TAB>platform<TAB>w<TAB>h<TAB>devicetype<TAB>orientation<TAB>split<TAB>manual"""
    devices, _ = cfg.devices()
    out = []
    for d in devices:
        plat = d.get("platform",
                     "mac" if str(d["name"]).startswith("mac") else "ipad")
        if want not in ("all", plat):
            continue
        out.append("\t".join(str(x) for x in (
            d["name"], plat, d["width"], d["height"],
            d.get("devicetype", ""), d.get("orientation", ""),
            d.get("split", ""), "1" if d.get("manual") else "")))
    return "\n".join(out)


# ──────────────────────────────── 自检 ────────────────────────────────
#
# 「没找到问题就算通过」的检查必须有一个**已知会失败**的样本证明它真的在
# 工作（规范 v4.0 阶段 S）。这里每一条都配一个反例。

def self_test() -> int:
    import tempfile
    import json
    ok = True

    def say(good: str, note: str):
        nonlocal ok
        ok &= bool(good)
        print(f"  {'PASS' if good else 'FAIL'}  {note}")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "swift").mkdir()
        (root / "swift/RootView.swift").write_text(
            'ScreenSpec(id: "alpha", title: "Alpha Screen")\n'
            'ScreenSpec(id: "beta",  title: "Beta Screen")\n', encoding="utf-8")
        (root / "ci.toml").write_text(
            'screens_source = "swift/RootView.swift"\n'
            '[shots]\n'
            'screens_kind = "screenspec"\n'
            'mac_app = "build/Demo.app"\n', encoding="utf-8")
        cfg = load(root)
        pairs = cfg.screens()
        say(pairs == [("alpha", "Alpha Screen"), ("beta", "Beta Screen")],
            "读到  screenspec 形状的两屏（id 与 title 成对）")
        say(cfg.get("mac_app") == "build/Demo.app",
            "读到  [shots] 里的 mac_app")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "swift").mkdir()
        (root / "spec").mkdir()
        (root / "swift/Screens.swift").write_text(
            'public static let sections: [(String, [String])] = [\n'
            '    ("Statics", ["A"]),\n'
            '    ("Beams", ["D", "E"]),\n'
            ']\n', encoding="utf-8")
        (root / "spec/specification.json").write_text(json.dumps({"modules": [
            {"id": "m_d", "family": "D", "tier": "core", "title": "Dee"},
            {"id": "m_a", "family": "A", "tier": "core", "title": "Ay"},
            {"id": "m_e", "family": "E", "tier": "extended", "title": "Ee"},
            {"id": "m_z", "family": "Z", "tier": "core", "title": "Zed"},
        ]}), encoding="utf-8")
        (root / "ci.toml").write_text(
            'canon = "spec/specification.json"\n'
            '[shots]\n'
            'screens_kind = "canon-sections"\n'
            'sections_source = "swift/Screens.swift"\n', encoding="utf-8")
        cfg = load(root)
        pairs = cfg.screens()
        say(pairs == [("m_a", "Ay"), ("m_d", "Dee")],
            "读到  canon-sections：分节表定顺序（A 在 D 前，尽管正典里 D 在前）")
        say(all(i != "m_e" for i, _ in pairs), "剔除  tier 不是 core 的模块")
        say(all(i != "m_z" for i, _ in pairs), "剔除  不属于任何分节的模块")

    # 反例 1：形状没声明时**报错**，不回落到猜。
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "ci.toml").write_text('slug = "demo"\n', encoding="utf-8")
        try:
            load(root).screens()
            say(False, "抓到  没声明 screens_kind 时报错（结果是它没报）")
        except SystemExit as exc:
            say("screens_kind" in str(exc),
                "抓到  没声明 screens_kind 时报错，不回落到猜")

    # 反例 2：声明了形状但一个都扫不出来 —— 零个画面不是通过。
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "swift").mkdir()
        (root / "swift/RootView.swift").write_text(
            "// 这里一个 ScreenSpec 也没有\n", encoding="utf-8")
        (root / "ci.toml").write_text(
            'screens_source = "swift/RootView.swift"\n'
            '[shots]\nscreens_kind = "screenspec"\n', encoding="utf-8")
        try:
            load(root).screens()
            say(False, "抓到  零个画面判未通过（结果是它放行了）")
        except SystemExit as exc:
            say("零个画面不是通过" in str(exc), "抓到  零个画面判未通过")

    # 档位来源要说得出是从哪读的 —— 两处位置不许静默等价。
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "ci.toml").write_text(
            '[[devices]]\nname="a"\nplatform="mac"\nwidth=1\nheight=2\n',
            encoding="utf-8")
        _, where = load(root).devices()
        say("[[devices]]" in where, "说出  档位读的是顶层 [[devices]]")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "ci.toml").write_text(
            '[[shots.devices]]\nname="a"\nplatform="mac"\nwidth=1\nheight=2\n',
            encoding="utf-8")
        devices, where = load(root).devices()
        say(len(devices) == 1 and "[[shots.devices]]" in where,
            "说出  档位读的是 [[shots.devices]]（闸门尚未接上）")

    print("\n自检通过——形状读取器确实在工作" if ok else "\n自检失败")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--shell", action="store_true")
    ap.add_argument("--describe", action="store_true")
    ap.add_argument("--screens", action="store_true", help="一行一个画面 id")
    ap.add_argument("--screen-titles", action="store_true")
    ap.add_argument("--tiers", choices=("mac", "ipad", "all"))
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        print("shots_config.py 自检")
        return self_test()

    cfg = load(args.root)
    if args.shell:
        print(emit_shell(cfg))
        return 0
    if args.screens:
        print("\n".join(i for i, _ in cfg.screens()))
        return 0
    if args.screen_titles:
        print("\n".join(t for _, t in cfg.screens()))
        return 0
    if args.tiers:
        print(tiers_tsv(cfg, args.tiers))
        return 0
    print(cfg.describe())
    return 0


if __name__ == "__main__":
    sys.exit(main())

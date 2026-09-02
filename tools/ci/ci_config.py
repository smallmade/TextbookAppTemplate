#!/usr/bin/env python3
"""共享工具链的项目配置读取器 —— `<项目根>/ci.toml`。

**这个文件存在的理由**：`tools/ci` 是三款 App 共用的一份真身（符号链接），
而它里面的脚本曾经把**某一款** App 的目录形状写死在源码里：

    FIGURE   = swift/Sources/StructureMechOneApp/FigureColumn.swift
    app_dir  = swift/Sources/MechanicsOneApp
    --python 默认 python/src        （热力学那一款的包在 src/thermo）
    --slug   默认 "structuremechone"

后果不是「在别的项目上报错」——那还好——而是**在别的项目上安静地报「尚不
适用」然后退 2**，于是 runner 把它印成一行黄色的跳过。实测：StructureMechOne
的 10 个跳过里有 5 个是「应该跑而没跑」，MechanicsOne 的通用 runner 把零依赖
纪律、对等测试、画面图形覆盖三道全跳过了，理由都是「尚未开始」，而三件事
全都早就做完了。

> 一道按别人的目录形状找不到东西、于是宣布自己不适用的闸门，
> 与一道通过了的闸门，在日志里长得一模一样。

所以形状由项目自己声明，写在项目根的 `ci.toml`；脚本读它。命令行参数仍然
优先——闸门要能被人手工指着任意路径跑。

**找不到 ci.toml 时**回落到自动探测（`src/` 与 `python/src/` 里找带
`__init__.py` 的包目录）。回落的判据只有一条，而且是刻意的：

> **一个都摸不到就是未通过，不是「干净」。**

用法：

    from ci_config import load, project_root
    cfg = load(root)                 # 读 <root>/ci.toml，缺了就自动探测
    pkg = cfg.path("python_package_dir")    # -> Path | None，已解析成绝对路径
    slug = cfg.get("slug")

shell 侧（run_all.sh、check_no_drift.sh）用：

    eval "$(python3 tools/ci/ci_config.py --root . --shell)"
    echo "$CI_PYTHON_PACKAGE_DIR"

键的清单见 KEYS。**未知的键不报错**（项目可以放自己的东西），但每一个被
脚本用到的键都必须列在 KEYS 里并带一句说明，否则 `--describe` 会漏掉它，
而一份没有人读得懂的配置文件两周之内就会漂。
"""

from __future__ import annotations

import argparse
import shlex
import sys
import tomllib
from pathlib import Path

#: 键 → 一句话说明。顺序即 `--describe` 的输出顺序。
KEYS: dict[str, str] = {
    "slug": "站点隔间名（https://smallmade.github.io/<slug>/），check_site.py 与 check_urls.sh 用",
    "runner": "CI 实际调用的那一个 runner（相对项目根）；没有 .github/workflows 时元闸门读它",
    "python_package_dir": "Python 包目录，含 kernel/composition/solve/dimension/ui 五层",
    "python_src_dir": "Python 包的父目录（放进 PYTHONPATH 的那一层）",
    "tests_dir": "pytest 的测试目录",
    "swift_app_dir": "SwiftUI 界面层目录（<Core>App）",
    "swift_kit_dir": "Swift 核心库目录（<Core>）",
    "canon": "开发正典",
    "shipped_canon": "剥离后的出货正典副本（构建产物）",
    "screens_source": "声明画面清单的 Swift 文件（如 RootView.swift）",
    "walkthrough_dir": "逐屏走查与设备矩阵截图的目录",
    "manual_paths": "两册手册的 HTML（使用手册、理论手册）",
    "app_bundles": "Gate S 要扫的成品（.app / .pkg / .ipa）",
    "site_dir": "站点目录",
    "listing": "商店文案正典（submission/LISTING.md）",
    "coverage_gaps": "未覆盖分支的说明文件（docs/coverage-gaps.md）",
    "figure_source": "图形派发的 Swift 源（check_figures.py 的 switch module.id 所在文件）",
    "evaluate_source": "按结构画图的登记表所在 Swift 源（openingFamily）",
    "latex_module": "渲染器所在的 Python 模块（如 mechanicskit.ui.latex）",
    "entitlements": "签名 entitlements 文件",
    "store_bundle_id": "上架版的 bundle id（check_packaging.py 用；桌面版必须与它不同）",
    "submodule_toolchain": "true 表示本项目【有意】以 submodule 持有工具链副本，check_no_drift.sh 据此把它与无意的实体副本分开",
    "help_bundle_dir": "打包进 App 的手册资源目录",
    "appiconset": "Assets.xcassets 里的 AppIcon.appiconset 目录（check_icon.py 用）",
    "devices": "设备矩阵的设备清单，每项 {name, width, height}",
    "appearances": "设备矩阵的外观清单（light / dark）",
}

#: 自动探测 Python 包时依次试的父目录。顺序有意义：项目自己声明的形状
#: 优先，其次是模板的默认（src/），最后是 MechanicsOne 那种 python/src/。
PACKAGE_PARENTS = ("src", "python/src", "python")


class Config:
    """一份 ci.toml，加上找不到它时的自动探测结果。"""

    def __init__(self, root: Path, data: dict, source: Path | None):
        self.root = root
        self.data = data
        self.source = source        # None 表示全靠自动探测

    # ---- 读 ----

    def get(self, key, default=None):
        return self.data.get(key, default)

    def path(self, key, default=None) -> Path | None:
        """一个键读成绝对路径。**不检查是否存在**——那是调用者的判断。"""
        value = self.data.get(key, default)
        if value in (None, ""):
            return None
        return (self.root / str(value)).resolve()

    def paths(self, key) -> list[Path]:
        value = self.data.get(key) or []
        if isinstance(value, str):
            value = [value]
        return [(self.root / str(v)).resolve() for v in value]

    def has(self, key) -> bool:
        return key in self.data and self.data[key] not in (None, "", [])

    # ---- 说明 ----

    def describe(self) -> str:
        where = self.source.name if self.source else "（无 ci.toml，自动探测）"
        lines = [f"项目配置 · {self.root}  ←  {where}"]
        for key, why in KEYS.items():
            if key in self.data:
                lines.append(f"  {key:<20} {self.data[key]!r}")
            else:
                lines.append(f"  {key:<20} —— 未声明（{why}）")
        extra = [k for k in self.data if k not in KEYS]
        for key in extra:
            lines.append(f"  {key:<20} {self.data[key]!r}   ← 不在 KEYS 里")
        return "\n".join(lines)


def detect_package(root: Path) -> Path | None:
    """找 Python 包目录：带 `__init__.py` 的那个。

    判据是 `__init__.py`，不是名字——名字会随项目变，而 egg-info 目录和
    `__pycache__` 会混进 `iterdir()` 的结果里（实测：`mechanicskit.egg-info`
    与 `mechanicskit` 并排躺着，取第一个就是 50% 的概率取错）。
    """
    for parent in PACKAGE_PARENTS:
        base = root / parent
        if not base.is_dir():
            continue
        candidates = sorted(d for d in base.iterdir()
                            if d.is_dir() and (d / "__init__.py").is_file())
        if candidates:
            return candidates[0]
    return None


def detect_swift(root: Path, kind: str) -> Path | None:
    """`kind` 是 "app" 或 "kit"。按目录名约定找，找不到返回 None。"""
    base = root / "swift" / "Sources"
    if not base.is_dir():
        return None
    dirs = sorted(d for d in base.iterdir() if d.is_dir())
    if kind == "app":
        for d in dirs:
            if d.name.endswith("App"):
                return d
        return None
    for d in dirs:
        if not d.name.endswith("App") and not d.name.endswith("Verify"):
            return d
    return None


def load(root: Path | str = ".") -> Config:
    """读 `<root>/ci.toml`；没有就自动探测，把探测结果填成同样的键。

    自动探测填的键只有能靠约定推出来的那几个。**推不出来的键不填**——
    填一个猜的值，就等于让下游脚本对着错的路径报「找不到，尚不适用」，
    而那正是这个模块要终结的失败模式。
    """
    root = Path(root).resolve()
    path = root / "ci.toml"
    data: dict = {}
    source: Path | None = None
    if path.is_file():
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        source = path

    if "python_package_dir" not in data:
        pkg = detect_package(root)
        if pkg:
            data["python_package_dir"] = str(pkg.relative_to(root))
    if "python_src_dir" not in data and "python_package_dir" in data:
        data["python_src_dir"] = str(
            Path(data["python_package_dir"]).parent)
    if "swift_app_dir" not in data:
        app = detect_swift(root, "app")
        if app:
            data["swift_app_dir"] = str(app.relative_to(root))
    if "swift_kit_dir" not in data:
        kit = detect_swift(root, "kit")
        if kit:
            data["swift_kit_dir"] = str(kit.relative_to(root))
    if "canon" not in data and (root / "spec" / "specification.json").is_file():
        data["canon"] = "spec/specification.json"
    if "tests_dir" not in data:
        for candidate in ("python/tests", "tests"):
            if (root / candidate).is_dir():
                data["tests_dir"] = candidate
                break
    if "site_dir" not in data and (root / "site").is_dir():
        data["site_dir"] = "site"
    if "listing" not in data and (root / "submission" / "LISTING.md").is_file():
        data["listing"] = "submission/LISTING.md"
    return Config(root, data, source)


#: shell 侧的变量名前缀。`slug` -> `CI_SLUG`。
def _shell_name(key: str) -> str:
    return "CI_" + key.upper()


def emit_shell(cfg: Config) -> str:
    """`eval` 得进 bash 的赋值行。列表用空格连接（路径含空格时加引号）。"""
    lines = []
    for key, value in cfg.data.items():
        name = _shell_name(key)
        if isinstance(value, (list, tuple)):
            rendered = " ".join(shlex.quote(str(v)) for v in value)
        elif isinstance(value, dict):
            continue                       # 表不进 shell，太容易走样
        else:
            rendered = str(value)
        lines.append(f"{name}={shlex.quote(rendered)}")
    lines.append(f"CI_CONFIG_SOURCE={shlex.quote(str(cfg.source or ''))}")
    return "\n".join(lines)


#: 对象计数的机器可读标记 —— 架构不变量 6 的后半句。
#:
#: 「查过了是干净的」与「没有东西可查」必须分得开。三款 App 各自付过学费：
#: `check_test_files.py` 在 2246 个测试面前数到 0 然后报通过；
#: `check_kernel_purity.sh` 对不存在的目录判「干净」；Gate S 的 S-4 在带
#: 空格的路径下一个文件都没打开就报绿。三次都是绿灯，三次都什么也没查。
#:
#: 所以每一道闸门都印一行这个，runner 把 N 印在结果行里，**N==0 即未通过**。
#: 标记刻意用 ASCII 且带等号，方便 bash 用 sed 抓，且不会撞上中文散文。
CHECKED = "CHECKED n={n} unit={unit}"


def checked(n: int, unit: str, note: str = "") -> str:
    """印一行对象计数，并返回它，方便调用处 `print(checked(...))`。

    `unit` 是这道闸门数的是什么：文件、模块、字串、行、画面……各脚本自定，
    因为「几个对象」在不同闸门上本来就不是同一种东西。写清楚比统一重要。
    """
    line = CHECKED.format(n=n, unit=unit)
    return f"{line}  —— 本次检查了 {n} {unit}{('，' + note) if note else ''}"


def self_test() -> int:
    """三个已知样本：一份显式配置、一次成功的自动探测、一次**失败**的探测。

    第三个是重点。自动探测摸不到包时必须返回 None，让调用者判未通过；
    上一版的等价代码在这里返回了一个空集合，于是 grep 零命中、闸门报绿。
    """
    import tempfile
    ok = True

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "ci.toml").write_text(
            'slug = "demo"\npython_package_dir = "weird/place/demokit"\n',
            encoding="utf-8")
        (root / "weird" / "place" / "demokit").mkdir(parents=True)
        cfg = load(root)
        good = (cfg.get("slug") == "demo"
                and cfg.path("python_package_dir").name == "demokit")
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  读取  显式 ci.toml 覆盖自动探测")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        pkg = root / "python" / "src" / "autokit"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (root / "python" / "src" / "autokit.egg-info").mkdir()
        cfg = load(root)
        found = cfg.path("python_package_dir")
        good = found is not None and found.name == "autokit"
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  探测  python/src 布局，"
              f"且不被 egg-info 骗走")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "src").mkdir()          # 空的：里面没有带 __init__.py 的包
        cfg = load(root)
        good = cfg.path("python_package_dir") is None
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  探测  摸不到包时返回 None"
              f"（调用者据此判未通过，不判干净）")

    print("\n自检通过——配置读取器确实在工作" if ok else "\n自检失败")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--shell", action="store_true", help="输出可 eval 的赋值行")
    ap.add_argument("--describe", action="store_true")
    ap.add_argument("--get", help="只印一个键的值（路径键印绝对路径）")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        print("ci_config.py 自检")
        return self_test()

    cfg = load(args.root)
    if args.get:
        value = cfg.get(args.get)
        if value is None:
            return 1
        print(value)
        return 0
    if args.shell:
        print(emit_shell(cfg))
        return 0
    print(cfg.describe())
    return 0


if __name__ == "__main__":
    sys.exit(main())

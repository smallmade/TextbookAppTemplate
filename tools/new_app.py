#!/usr/bin/env python3
"""新项目骨架生成器 —— 规范 v4.0 阶段 D2。

    python tools/new_app.py --slug thermo --core ThermoKit --title "Thermo Tables"

一条命令生成完整骨架，把「每次都要重新决定的事」压缩到零。

生成出来的项目**一开始所有测试都是红的，这是正确状态**：阶段 02 要求
验证资产先于核心存在，所以骨架里预置的测试全部指向还不存在的实现。
逐条把它们变绿，就是阶段 03 的全部工作。

刻意不生成的东西：
  - 许可证签发系统（桌面版自用不销售，那套东西是净负担）
  - 教材 PDF 的任何副本（.gitignore 里已经排除）
  - 任何形式的运行时开关（架构不变量 4）
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

TEMPLATE_ROOT = Path(__file__).resolve().parent.parent


# ── 骨架内容 ──────────────────────────────────────────────────────

GITIGNORE = """\
# 教材 PDF 永不进版本控制（规范 § 著作权与合规 第 1 条）。
# 它们体积大、受版权保护，而且工具链不依赖它们——审计脚本只 import 核心，
# 没有书也能跑。放在仓库外的 refs/ 里，路径记在 docs/charter.md。
*.pdf
refs/

# 构建产物
build/
dist/
.build/
__pycache__/
*.pyc
.pytest_cache/
.coverage
htmlcov/

# 提交产物：递归匹配。单层 * 不跨目录分隔符，
# 而 uploads/ 下还有一层 old/ 放被取代的包（实测踩过，几十 MB 进了 git）。
submission/uploads/**/*.pkg
submission/uploads/**/*.ipa
submission/uploads/**/*.dSYM

# Xcode
*.xcuserdatad/
DerivedData/
"""

SPEC_SKELETON = {
    "meta": {
        "app": "{TITLE}",
        "domain": "{SLUG}",
        "spec_version": "0.1.0",
    },
    "sources": [
        {
            # key 用角色名，不要用作者姓氏——字段剥干净不等于内容剥干净
            "key": "primary-textbook",
            "author": "TODO",
            "title": "TODO",
            "edition": "TODO",
            "year": 0,
            "role": "primary",
            "licence": "copyrighted",
            "ship": False,
        },
        {
            "key": "independent-check",
            "author": "TODO —— 优先选公有领域来源（NACA / NIST / IAPWS）",
            "title": "TODO",
            "edition": "",
            "year": 0,
            "role": "independent-check",
            "licence": "public-domain",
            "ship": True,
        },
    ],
    "meanings": {
        "_TODO": "每个出现在 entries/outputs 的符号都要有一条，用你自己的话写",
    },
    "modules": [
        {
            "id": "example_module",
            "title": "TODO",
            "citation": "TODO —— 精确到式号，如 Gere 9th ed. §5.3, Eq. 5-12",
            "formula_display": "TODO —— LaTeX，界面上直接展示；不含教材标识",
            "tier": "core",
            "summary": "TODO",
            "entries": [],
            "outputs": [],
            "branching": [],
            "invariants": [],
            "trends": [],
            "boundaries": [],
            "parameterisations": [],
        }
    ],
    "validity": [],
    "build": {
        "strip_on_ship": ["citation", "sources[].author", "sources[].title"]
    },
}

CHARTER = """\
# {TITLE} —— 立项书

阶段 00 的产出。**六项检核全过才进阶段 01。** 任何一项不过，记录理由并换题。

## 六项检核

| # | 检核 | 是/否 | 依据 |
|---|---|---|---|
| 1 | 算式闭式但非平凡（需迭代求根、超越方程或查表插值） | | |
| 2 | 输入维度低（能放进一个手机屏幕，不需要建模） | | |
| 3 | 有既存工作流被取代（查表、查图、翻附录） | | |
| 4 | 课程全球标准化（必修、教材集中在少数几部） | | |
| 5 | 可交互、可视化（拖一个参数，图会变） | | |
| 6 | **存在独立第二源** ★ | | |

第 6 项是最重要的一条：前五层验证全部追溯回同一部书，你对那部书的误读会被
忠实复制到每一层，而每一个测试都会通过。只有一个独立来源能抓到这种错。

## 来源声明

| 角色 | 作者/机构 | 名称 | 版次/年 | 许可 | 出货 |
|---|---|---|---|---|---|
| 主教材 | | | | copyrighted | 否 |
| 独立第二源 | | | | public-domain | 是 |

**主教材 PDF 存放位置**（仓库外）：`TODO`
**第二源确实不衍生自主教材的依据**：`TODO`

## 一句话产品定义

> TODO —— 后续所有文案由它派生。阶段 04 之前不得修改。

## 命名

两条硬规则：

- [ ] 关键词开头，品牌收尾（`Beam & Stress — {TITLE}` 对；`{TITLE}: Beam` 错）
- [ ] **不含 Apple 商标词**（Mac / iPhone / iPad / iOS / macOS / Apple / Watch …）

拟定名称：`TODO`
拟定副标题（≤30 字符）：`TODO`

## 纳入章节

TODO

## 不做清单

阶段 04 之前不得修改。至少回答三个问题：

- 不纳入哪几章，理由是什么？
- 哪些工况明确不支持？
- 哪些是「v2 再说」而不是「永远不做」？（两者要分开写）

TODO
"""

COVERAGE_AUDIT = """\
# {TITLE} —— 适配审计

阶段 04 的产出。回答的问题是：**教材课后习题，这个 App 能不能「摆得出来」？**

---

## 这不是正确性指标

> 课本多半不印课后题答案、也没有解答手册，本报告里的每一个数字都是**被测
> 程序自己算的**。它衡量的是**产品适配度，不是对错**。正确性由阶段 02 的
> 五层验证负责，与本文件无关。

这段声明必须逐字保留。少了它，半年后很容易把「92% 的题目能摆出来」误读成
「92% 的题目答案正确」。

---

## 判定

| 判定 | 意思 | 处置 |
|---|---|---|
| `ok` | 直接可摆 | 无 |
| `awkward` | 摆得出来但要绕路 | 评估是否值得加一个入口 |
| `gap` | 摆不出来 | 修掉，或写进不做清单——不许留白 |
| `n/a` | 不在范围内（推导题、论述题） | 无 |

## 结果

| 章 | 题号 | 判定 | 备注 |
|---|---|---|---|
| | | | |

## gap 处置

| gap | 处置（修掉 / 写进不做清单） | 理由 |
|---|---|---|
| | | |
"""

KERNEL_INIT = '''\
"""{CORE} · kernel —— 单一关系式的纯函数层。

**架构不变量 1：零运行期依赖。** 这个目录里只允许 import 标准库的 math
与本包自身。这不是风格偏好——零依赖的东西才能同时活在 Python、Swift 甚至
C++ 里，而整个跨平台架构就建立在这一条上面。

**架构不变量 2：不含平台代码。** 不知道单位、不知道界面、不做决策。
没有文件读写，没有 GUI 库，没有操作系统调用。

两条都由 tools/ci/check_kernel_purity.sh 机器验证。
"""

import math  # noqa: F401  —— 唯一允许的外部 import
'''

LAYER_DOCS = {
    "composition": '把 kernel 串成有意义的工况（多段、串接）。不处理输入解析。',
    "solve": '反算：给定输出求输入；多解消歧。不决定显示格式。',
    "dimension": '单位换算与量纲检查，边界处一次做完。内部一律 SI，不流出去。',
    "ui": (
        '显示决策层：有效位数、警告触发、字段启用。\n\n'
        '**这一层不 import 任何 GUI 库。** PySide6 前端与 SwiftUI 前端共用\n'
        '同一组决策——「什么时候显示黄色警告」「这个字段要不要禁用」这类逻辑\n'
        '只写一次、只测一次，也只需要跨语言比对一次。\n\n'
        '它是阶段 05 对等测试的五个受检层之一。'
    ),
}

TEST_SPEC = '''\
"""Gate 01 —— 正典自检。

这个测试在写任何核心代码之前就应该变绿。
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "spec" / "specification.json"


def test_spec_passes_gate_01():
    """正典必须通过 Gate 01 的全部条件。"""
    checker = ROOT / "tools" / "ci" / "check_spec.py"
    if not checker.exists():
        checker = Path("{TEMPLATE_ROOT}") / "tools" / "ci" / "check_spec.py"
    result = subprocess.run(
        [sys.executable, str(checker), str(SPEC)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_spec_is_valid_json():
    json.loads(SPEC.read_text(encoding="utf-8"))
'''

CI_WORKFLOW = """\
name: CI
on: [push, pull_request]

jobs:
  gates:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: 安装依赖
        run: pip install -e '.[dev]'
      - name: 十二项闸门
        run: bash tools/ci/run_all.sh .
"""

PYPROJECT = """\
[project]
name = "{SLUG}"
version = "0.1.0"
description = "{TITLE}"
requires-python = ">=3.11"
dependencies = []          # 核心零运行期依赖 —— 架构不变量 1

[project.optional-dependencies]
dev = ["pytest", "pytest-cov", "hypothesis", "mpmath", "sympy"]
ui  = ["PySide6"]          # 只有桌面版需要；核心与验证都不碰它

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.coverage.run]
branch = true
source = ["src/{PKG}"]
"""

README = """\
# {TITLE}

依《教材型 App 建造规范 v4.0》生成。**当前处于阶段 01：正典尚未写完，
所有测试都是红的——这是正确状态。**

## 现在该做什么

```bash
# 1. 填 docs/charter.md（阶段 00 的六项检核 + 不做清单）
# 2. 写 spec/specification.json
python tools/ci/check_spec.py spec/specification.json    # Gate 01
# 3. 建五层 fixture（阶段 02），此时核心仍未实现
# 4. 让红灯逐条变绿（阶段 03）
```

## 十二项闸门

```bash
bash tools/ci/run_all.sh .
```

| 闸门 | 命令 |
|---|---|
| 01 正典 | `check_spec.py` |
| 02 充分性 | `check_sufficiency.py` |
| 02 格式矩阵 | `check_input_matrix.py` |
| 03 零依赖 | `check_kernel_purity.sh` |
| 05 对等 | `check_port_coverage.py` |
| 06 法律隔离 | `check_legal_isolation.sh` |
| S 二进制卫生 | `check_binary_hygiene.sh` |
| 07 文案字数 | `check_listing_limits.py` |
| 07 截图尺寸 | `check_screenshots.py` |
| 07 站点可达 | `check_urls.sh` |
| 08 plist | `check_plists.sh` |
| 08 entitlements | `check_entitlements.sh` |
| 09 许可 | `audit_licences.py` |
"""


# ── 生成 ──────────────────────────────────────────────────────────

def write(path: Path, content: str, subs: dict) -> None:
    for key, value in subs.items():
        content = content.replace("{" + key + "}", value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  {path}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slug", required=True, help="短名，如 thermo")
    ap.add_argument("--core", required=True, help="核心库名，如 ThermoKit")
    ap.add_argument("--title", required=True, help="产品名，如 Thermo Tables")
    ap.add_argument("--dest", default=".", help="生成到哪个目录（默认当前目录）")
    args = ap.parse_args()

    if not re.fullmatch(r"[a-z][a-z0-9_-]*", args.slug):
        print(f"错误：--slug 必须是小写字母开头的短名，得到 {args.slug!r}", file=sys.stderr)
        return 2

    # 命名硬规则（规范 阶段 07 · 7-A）。在生成阶段就拦，比上架被拒便宜得多。
    APPLE_MARKS = ("mac", "iphone", "ipad", "ios", "apple", "watch",
                   "vision", "airplay", "retina")
    low = args.title.lower()
    hits = [m for m in APPLE_MARKS if re.search(rf"\b{m}", low)]
    if hits:
        print(f"错误：产品名含 Apple 商标词 {hits} —— Guideline 5.2.5 会拒。",
              file=sys.stderr)
        print("      「Plot4Mac」就是这样被拒的，改名 PlotOne 才过。", file=sys.stderr)
        return 2

    root = Path(args.dest).resolve() / args.slug
    if root.exists() and any(root.iterdir()):
        print(f"错误：{root} 已存在且非空", file=sys.stderr)
        return 2

    pkg = args.core.lower().replace("kit", "kit")
    subs = {"SLUG": args.slug, "CORE": args.core, "TITLE": args.title,
            "PKG": pkg, "TEMPLATE_ROOT": str(TEMPLATE_ROOT)}

    print(f"\n生成 {args.title} → {root}\n")

    write(root / ".gitignore", GITIGNORE, subs)
    write(root / "README.md", README, subs)
    write(root / "pyproject.toml", PYPROJECT, subs)
    write(root / "docs" / "charter.md", CHARTER, subs)
    write(root / "docs" / "coverage-audit.md", COVERAGE_AUDIT, subs)
    write(root / ".github" / "workflows" / "ci.yml", CI_WORKFLOW, subs)

    spec = json.dumps(SPEC_SKELETON, ensure_ascii=False, indent=2)
    write(root / "spec" / "specification.json", spec, subs)

    # 五层
    write(root / "src" / pkg / "kernel" / "__init__.py", KERNEL_INIT, subs)
    for layer, doc in LAYER_DOCS.items():
        write(root / "src" / pkg / layer / "__init__.py",
              f'"""{args.core} · {layer} —— {doc}\n"""\n', subs)
    write(root / "src" / pkg / "__init__.py",
          f'"""{args.core} —— 零依赖核心，五层。"""\n', subs)

    # 测试骨架：一开始全红，逐条变绿就是开发过程
    write(root / "tests" / "test_spec.py", TEST_SPEC, subs)
    for name, gate in [("test_sufficiency", "Gate 02 七条充分性判据"),
                       ("test_input_matrix", "Gate 02 输入格式矩阵"),
                       ("test_port_coverage", "Gate 05 对等测试"),
                       ("test_kernel_discipline", "Gate 03 零依赖纪律")]:
        write(root / "tests" / f"{name}.py",
              f'"""{gate}。\n\n'
              f'骨架阶段这个测试是红的，这是正确状态——阶段 02 要求验证资产\n'
              f'先于核心存在。让它变绿就是接下来的工作。\n"""\n\n'
              f'import pytest\n\n\n'
              f'@pytest.mark.xfail(reason="骨架阶段：实现尚未开始", strict=False)\n'
              f'def test_placeholder():\n'
              f'    raise NotImplementedError("{gate}")\n', subs)

    write(root / "tests" / "data" / "SOURCE.md",
          "# fixture 来源\n\n"
          "每一份联网获取的 fixture 旁边都必须有一条记录：URL、获取日期、\n"
          "数据本身的出处名称与许可状态。\n\n"
          "| 文件 | URL | 获取日期 | 出处 | 许可 |\n|---|---|---|---|---|\n", subs)

    # submission 套件（阶段 07/08）
    write(root / "submission" / "LISTING.md",
          f"# {args.title} —— 商店文案\n\n"
          f"## 字数上限（入套件前机器校验）\n\n"
          f"| 字段 | 上限 |\n|---|---|\n"
          f"| Subtitle | 30 |\n| Promotional Text | 170 |\n"
          f"| Keywords | 100 |\n| Description | 4000 |\n\n"
          f"## App Name（30）\n\n```\n{args.title}\n```\n\n"
          f"## Subtitle（30）\n\n```\nTODO —— 关键词开头，品牌收尾\n```\n\n"
          f"## Description（4000）\n\n```\nTODO —— 头两行说清覆盖范围（模块清单，"
          f"不是形容词）。GL 4.2 看的就是这里。\n```\n\n"
          f"## Keywords（100，逗号分隔无空格）\n\n```\nTODO\n```\n", subs)

    print(f"""
骨架已生成。

  cd {root}
  pip install -e '.[dev]'
  bash {TEMPLATE_ROOT}/tools/ci/run_all.sh .

**现在所有测试都是红的，这是正确状态。** 阶段 02 要求验证资产先于核心
存在，所以预置的测试全部指向还不存在的实现。逐条变绿就是阶段 03。

下一步：填 docs/charter.md 的六项检核，然后写 spec/specification.json。
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())

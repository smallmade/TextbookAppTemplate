# TextbookAppTemplate

《教材型 App 建造规范 v4.0》的技术储备。规范说「应该怎么做」，这里是
**能跑的东西**。

v2.0 的「标准化与提效」章列了四项投入，但那些全是提案——规范里写着
`python tools/new_app.py --slug thermo`，而那个脚本不存在。这个仓库把它们
建出来。

---

## 一条命令开新项目

```bash
python3 tools/new_app.py --slug thermo --core ThermoKit --title "Steam Tables — ThermoOne"
```

生成完整骨架：目录结构、spec 骨架、五层 Python 包、立项书模板、适配审计
模板、CI workflow、`.gitignore`（教材 PDF 已排除）、submission 套件。

**生成出来的项目一开始所有测试都是红的，这是正确状态。** 阶段 02 要求验证
资产先于核心存在，所以预置的测试全部指向还不存在的实现。逐条变绿就是
阶段 03 的全部工作。

生成阶段就拦的两件事：

- **产品名含 Apple 商标词直接拒绝** —— 「Plot4Mac」就是这样被 GL 5.2.5 拒的
- **教材 PDF 进 `.gitignore`** —— 且产物排除用 `**/*.pkg` 递归匹配（单层 `*`
  不跨目录分隔符，实测让几十 MB 二进制进了 git）

---

## 工具链只有一份真身

各项目的 `tools/ci` 是**指向本仓库的符号链接**，不是副本：

```bash
ln -sfn ../../TextbookAppTemplate/tools/ci "<项目>/tools/ci"
bash tools/ci/check_no_drift.sh <APP-Development 目录>    # 守着它还是链接
```

**为什么要有这条规矩。** 2026-08-29 的实况：五个 Claude Code 会话同时写同一个
Google Drive 文件夹，四个项目各持一份 `tools/ci` 副本。副本里有两项真改进
（docstring 误报的两处修复、出货副本双复查），也有三份已经过期的旧版——
**而没有任何东西在看这件事**，直到有人问「strip_spec.py 从哪来」才发现。

**要改工具：改这里的真身，别在项目里就地改。** 真要就地试，试完提升回模板再
把链接接回去——沉淀不回去的改进，下一个项目享受不到，而且会静默过期。

---

## 十四项闸门

```bash
bash tools/ci/run_all.sh <项目目录>
```

| 检查 | 闸门 | 守的是 |
|---|---|---|
| `check_spec.py` | Gate 01 | 正典合法、citation 精确到式号、每个符号有释义 |
| `check_sufficiency.py` | Gate 02 | 七条充分性判据 + **黄金律**（层 2 生成脚本不得 import 核心） |
| `make_input_matrix.py` | Gate 02 | 生成格式矩阵 fixture（成对覆盖 + 已知致命组合） |
| `check_input_matrix.py` | Gate 02 | 矩阵齐备 · fixture 未被 git 改坏 · **读取器实测** |
| `check_kernel_purity.sh` | 不变量 1、2 | kernel 零依赖；四层不含平台代码 |
| `check_port_coverage.py` | Gate 05 | 对等测试，五层全覆盖，自动探索 |
| `check_legal_isolation.sh` | Gate 06 | 界面层无教材标识、无物理常数 |
| `check_binary_hygiene.sh` | **Gate S** | **出货二进制的行为封闭性** |
| `check_listing_limits.py` | Gate 07 | 文案字数 + 命名两条硬规则 |
| `check_screenshots.py` | Gate 07 | ASC 实测尺寸 |
| `check_urls.sh` | Gate 07 | 站点五个 URL 回 200 |
| `check_plists.sh` | Gate 08 | plist 规范化 + 严格解析 |
| `strip_spec.py` | Gate 01/06 | 产出出货副本 + 剥完后按内容回扫 |
| `check_ship_isolation.py` | Gate 06 | 独立复查出货副本的**每一个字符串** |
| `audit_licences.py` | Gate 09 | 无 GPL-only 组件；LGPL 三项条件 |
| `check_no_drift.sh` | — | 工具链未分叉 |

### 退出码约定

```
0 = 通过
1 = 未通过
2 = 本阶段尚不适用（跳过）
```

**第三种是必要的。** 一道在内容还没写时就报「通过」的闸门是静默放行——
它会让人以为这一项已经查过了。`run_all.sh` 把 2 显示为「跳过」并说明原因。

### 每道闸门都能自证还活着

写这批脚本时被自己咬了三次，全部固化成自检：

| 事故 | 现在怎么防 |
|---|---|
| 过滤模式以 `--` 开头，grep 当成选项报错退出，`\|\| true` 吞掉错误 → 报告「零命中 ✓」 | 脚本开头用**必然命中**的样本走完整管线 |
| `(PySide\|…)\b` 匹配不上 `PySide6`（两者之间没有词边界）→ 静默放行真违规 | **双向**自检：真违规必须抓到，谈论 GUI 库的散文必须不误判 |
| 裸词匹配把文档字串里「这一层不 import 任何 GUI 库」判成违规 | 只匹配真正的 import 语句 |

> **凡是「没找到问题就算通过」的检查，都必须有一个已知会失败的样本证明它
> 真的在工作。** 一道静默放行的闸门比没有闸门更糟：没有闸门时你至少知道
> 自己没检查。而一道会乱叫的闸门，两天之内就会被关掉。

---

### fixture 目录约定

`check_sufficiency.py` 要知道「哪个 fixture 属于哪个 module、哪一层」。约定
用目录编码——目录是文件系统里唯一不会和内容不同步的元数据：

```
tests/data/
  layer1-printed/<module_id>[-<suffix>].csv      层 1 印刷表格（4 位）
  layer2-highprec/<module_id>[-<suffix>].csv     层 2 高精度（20 位）
  layer2-highprec/generate_<module_id>.py        层 2 的生成脚本
  layer3-symbolic/<module_id>[-<suffix>].py      层 3 符号验证
  layer5-secondsource/<module_id>[-<suffix>].csv 层 5 独立第二源
  matrix/                                        输入格式矩阵（自动生成）
  examples/<module_id>.csv                       教材章内例题
  SOURCE.md                                      联网 fixture 的留证
```

层 4 不放 fixture——它由正典的 invariants / trends / boundaries 自动派生。

### 三件容易被忽略、但这批闸门专门守的事

**黄金律。** 层 2 的生成脚本一旦 `import` 了核心，那一层就变成自证——用被测
程序生成参考值，测试永远绿灯却什么都没证明。`check_sufficiency.py` 解析
每个 `generate_*.py` 的 AST，import 到核心包就直接失败。

**git 会毁掉 CRLF fixture。** `core.autocrlf` 与 `text=auto` 会在检出时把 CRLF
规范化成 LF——**一个专门用来测 CRLF 的 fixture 被改成 LF，测试照样绿灯，而
缺陷原样还在。** 所以项目根要有：

```
tests/data/matrix/** -text -diff
```

`check_input_matrix.py` 会逐字节比对并核对这一行在不在。

**不可表示的组合不该生成。** U+2028 在 Latin-1 里根本不存在。第一版用
`errors="replace"` 把它换成了 `?`，生成出一个本身就无效的 fixture，然后要求
读取器把它解析成 6 行——读取器怎么做都是错的。**一个不该存在的测试用例，比
没有测试用例更糟。** 现在这类组合直接剔除并报出来。

---

## EngKit —— 跨 App 共享层

```
engkit/python/engkit/     roots · interp · units · spec
engkit/swift/Sources/     Roots.swift · Units.swift · Spec.swift
```

**零依赖**：只用标准库。EngKit 会被 import 进各 App 的 kernel 上层，如果它
自己带依赖，架构不变量 1 就名存实亡了。

**两端同名同结构同数值**，这是阶段 05 对等测试比对的对象。Swift 侧 8 项
测试全绿，其中「数值与 Python 侧逐位一致」这一条在写的时候就抓到了一个
手打的错误期望值——**黄金律在工具层同样成立：参考值必须独立算出来。**

| 模块 | 内容 | 为什么共享 |
|---|---|---|
| `roots` | brentq · bisect | 选题闸第 1 项就是「需迭代求根」，每款都要 |
| `interp` | linear · bilinear | 蒸汽表、Moody 图、物性表都是查表插值 |
| `units` | to_si · from_si | dimension 层纪律：内部一律 SI，换算只在边界做一次 |
| `spec` | load · digest · **strip_for_ship** | 架构不变量 3；剥离是法律隔离第一道防线 |

`strip_for_ship` 的一个要点：**sources 按许可判断，不一刀切**。受版权来源
剥掉 author/title；公有领域来源（NACA / NASA / NIST / IAPWS / CODATA）
**保留并且应当具名**——规范明确写着具名它们反而增强可信度且零风险。第一版
在这里一刀切，把 NIST 的署名也剥掉了，方向正好反了。

**版本纪律**：语义化版本，每个 App pin 一个具体 tag，不用 main。否则改动
EngKit 会同时打破七个 App，而你不会知道是哪一次改动干的。

---

## 上架工具链

| 工具 | 用途 |
|---|---|
| `tools/ledger/builds.md` | 构建号台账。**号只增不减**，投递前查 ASC 确认未占用 |
| `tools/shots/capture_ios.sh` | 截图采集——**脚本驱动真实交互，不用运行时钩子** |
| `tools/shots/resize_for_asc.py` | 按 ASC 实测尺寸转换（iPhone 1284×2778） |

截图这条链路是重写过的。老路线是在 App 里留一个环境变量开关、启动时预设
界面状态（PlotOne 的 `QAHooks` 就是这么来的）——那导致了 **Guideline 5.6
账号层拒审**。新路线慢一些、需要为每款 App 写一段坐标序列，但出货二进制里
不会留下任何开关。

`PortfolioKit/tools/` 里的签名与打包脚本继续有效，两边配合使用。

---

## 目录

```
TextbookAppTemplate/
├── tools/
│   ├── new_app.py              骨架生成器
│   ├── ci/                     十二项闸门 + run_all.sh
│   ├── shots/                  截图采集与尺寸转换
│   └── ledger/builds.md        构建号台账
└── engkit/
    ├── python/engkit/          Python 侧
    └── swift/                  Swift 侧（swift test 全绿）
```

#!/bin/bash
# 本项目的全闸门。任何一项失败即整体失败。
#
#   bash tools/ci/run_gates.sh
#
# 顺序有意义：正典先于代码，架构不变量先于测试，跨语言比对在两侧都成立
# 之后。阶段 05 之后的闸门（Swift 对等、conformance、法律隔离、二进制卫生）
# 在对应产物存在之前跳过并标注为【尚未到达】——不是通过。一道报告
# 「零命中 ✓」而其实没有运行的闸门，比没有闸门更糟。
#
# ── 这个文件自己犯过四次它抬头警告的那个错（2026-09-03 修）────────────────
#
# 1. `check_kernel_purity.sh` 收到的是【另一款 App 的】包目录（src/thermo）。
#    那个目录在别处不存在，脚本印一行用法然后退 2 —— 零依赖纪律从来没被这个
#    runner 查过，而日志里它只是一行红字，看起来像一道正在工作的闸门。
# 2. `tools/build/codegen_data.py` 同样是另一款 App 的文件。本项目没有生成表，
#    这一步于是每次都以「文件不存在」失败。**一道恒红的闸门和一道恒绿的闸门
#    一样没有信息量**，两者都会在两周内被人当成背景噪音。
# 3. 阶段 05/06/07/S 四行 `pending` 是【写死的字符串】。swift/、site/、
#    submission/、dist/ 早就都在了，四道闸门却继续印「尚未到达」。
#    一个手写的状态标记只要跟着别的东西一起改，就会漂，而漂掉的那一刻
#    没有任何东西会失败。
# 4. `check_legal_isolation.sh` 与 `check_manual_isolation.py` 一次也没被调用。
#
# 四条的病根是同一个：**配置被写进了源码**。所以现在路径一律读 `ci.toml`
# （见 `tools/ci/ci_config.py`），读不到就自动探测；「尚未到达」只在产物
# 真的不存在时才印；而每一道「没找到问题就算通过」的闸门旁边配一个
# **已知不合格样本**（`must_fail`）——一道跑得起来却不可能失败的闸门，
# 是同一个缺陷换了身衣服。
set -uo pipefail
cd "$(dirname "$0")/../.."

# ── 项目形状：读 <项目根>/ci.toml，读不到就按约定自动探测 ─────────────────
# 写死任何一款 App 的目录形状，正是上面四条的成因。命令行仍可覆盖。
eval "$(python3 tools/ci/ci_config.py --root . --shell 2>/dev/null || true)"
PKG="${CI_PYTHON_PACKAGE_DIR:-}"
SRCDIR="${CI_PYTHON_SRC_DIR:-src}"
KIT="${CI_SWIFT_KIT_DIR:-}"
APP="${CI_SWIFT_APP_DIR:-}"
CANON="${CI_CANON:-spec/specification.json}"
SLUG="${CI_SLUG:-}"
LISTING="${CI_LISTING:-submission/LISTING.md}"
SHIPPED="build/specification.shipped.json"
SHOTS="submission/screenshots"

export PYTHONPATH="${SRCDIR}:engkit/python${PYTHONPATH:+:$PYTHONPATH}"

RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; OFF=$'\033[0m'
PASS=0; FAIL=0; SKIP=0; FAILED_NAMES=()

_fail() { echo "  ${RED}✗ 未通过${OFF}${1:+  $1}"; FAIL=$((FAIL+1)); FAILED_NAMES+=("$CUR"); }

step() { CUR="$1"; echo; echo "── $1 ──"; shift
    if "$@"; then echo "  ${GREEN}✓${OFF}"; PASS=$((PASS+1)); else _fail; fi; }

# 三态。退出码 2 =「本阶段尚不适用」，但它必须【说出为什么】，而且不能是
# argparse 的参数用法错误——那也是退出码 2，把它印成一行黄色的跳过，正是
# 静默放行。判据与 run_all.sh 一字不差。
NA_PREFIX='(尚)?不适用|not applicable|NOT_APPLICABLE'
ARGPARSE='(^|[^A-Za-z])(usage:|error:)|the following arguments are required|unrecognized arguments|invalid choice|expected one argument|用法[:：]'
gate() { CUR="$1"; echo; echo "── $1 ──"; shift
    local out code; out="$("$@" 2>&1)"; code=$?
    echo "$out" | sed 's/^/  /'
    case $code in
        0) echo "  ${GREEN}✓${OFF}"; PASS=$((PASS+1)) ;;
        2) if echo "$out" | grep -qE "$ARGPARSE"; then
               _fail "退出码 2 来自参数用法错误，不是「尚不适用」"
           elif echo "$out" | grep -qE "$NA_PREFIX"; then
               echo "  ${YELLOW}⋯ 尚未到达${OFF}（理由见上）"; SKIP=$((SKIP+1))
           else
               _fail "退出 2 却没有说「尚不适用」以及为什么"
           fi ;;
        *) _fail ;;
    esac; }

# 产物本该在而不在 —— 这不是跳过，是未通过。
missing() { CUR="$1"; echo; echo "── $1 ──"; _fail "$2"; }

# 产物确实还没有。理由是【算出来的】，不是写死的阶段名。
pending() { echo; echo "── $1 ──"; echo "  ${YELLOW}⋯ 尚未到达${OFF}：$2"; SKIP=$((SKIP+1)); }

# 已知不合格样本：命令【必须】非零退出，且理由必须是我们要它抓的那一个。
# 只断言「非零」不够——一道因为路径打错而红的闸门，和一道真的抓到东西的
# 闸门，退出码长得一模一样（本文件第 1 条就是这么漏过去的）。
must_fail() { CUR="$1"; local want="$2"; shift 2
    echo; echo "── $CUR ──"
    local out code; out="$("$@" 2>&1)"; code=$?
    if [ "$code" -eq 0 ]; then
        _fail "已知不合格样本【通过了】—— 这道闸门抓不到它该抓的东西"
    elif ! grep -qF "$want" <<<"$out"; then
        _fail "样本被拒了，但理由不是「$want」—— 红得不是地方"
        echo "$out" | grep -v '^[[:space:]]*$' | tail -3 | sed 's/^/      /'
    else
        echo "  ${GREEN}✓${OFF} 已知不合格样本被抓到：$want"; PASS=$((PASS+1))
    fi; }

mkdir -p build

# ── 已知不合格样本 ────────────────────────────────────────────────────────
# 一律建在 /tmp：本系列的仓库放在 Google Drive 上，File Provider 会给文件补
# FinderInfo，中间产物留在仓库里会让 codesign 报 resource fork detritus。
BAD="$(mktemp -d "${TMPDIR:-/tmp}/known-bad.XXXXXX")" || exit 1
trap 'rm -rf "$BAD"' EXIT

mkdir -p "$BAD/purity/kernel"
printf 'import numpy as np\n' > "$BAD/purity/kernel/leak.py"

for _layer in kernel composition solve ui dimension; do
    mkdir -p "$BAD/port/py/$_layer"
    printf 'def only_in_python_probe(x):\n    return x\n' > "$BAD/port/py/$_layer/probe.py"
done
mkdir -p "$BAD/port/swift"
printf 'let unrelated = 1\n' > "$BAD/port/swift/Empty.swift"

# 式号是【表达】，不是事实。用编号体系而不是某个作者姓氏当样本：姓氏名单
# 是从正典派生的，换一个项目就换一批，而 `Eq. 5-12` 在哪一款上都该被抓到。
mkdir -p "$BAD/legal"
printf 'let note = "as derived in Eq. 5-12 of the source text"\n' > "$BAD/legal/Leak.swift"

cat > "$BAD/LISTING.md" <<'BADLISTING'
## App Name

```
Probe Build
```

## Subtitle

```
this subtitle is deliberately longer than thirty characters
```

## Promotional Text

```
probe
```

## Keywords

```
probe,sample
```

## Description

```
probe
```
BADLISTING

mkdir -p "$BAD/shots/mac"
python3 - "$BAD/shots/mac/wrong-size.png" <<'BADPNG'
import pathlib, struct, sys, zlib
def chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
ihdr = struct.pack(">II5B", 100, 100, 8, 2, 0, 0, 0)   # 100x100：哪一档都不是
pathlib.Path(sys.argv[1]).write_bytes(
    b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IEND", b""))
BADPNG

# ══ Gate 01 · 正典 ════════════════════════════════════════════════════════
step "Gate 01 · 开发正典" \
     python3 tools/ci/check_spec.py "$CANON"
step "Gate 01 · 剥离出货副本" \
     python3 tools/ci/strip_spec.py "$CANON" "$SHIPPED"
step "Gate 01 · 出货副本复检" \
     python3 tools/ci/check_spec.py --shipped "$SHIPPED"
step "自检 · 正典闸门抓得到已知不合格样本" \
     python3 tools/ci/check_spec.py --selftest "$CANON"
# `--python src` 是同一类写死：包树位于 python/src 的那一款上它指向一个不
# 存在的目录，check_canon_functions.py 于是印「尚不适用」并以退出码 2 结束，
# 而 runner 把它记成「未通过」——【未通过】与【根本没查】又一次长得一样。
if [ -d "$SRCDIR" ]; then
    step "Gate 01+ · 正典 function 指针可解析" \
         python3 tools/ci/check_canon_functions.py "$CANON" --python "$SRCDIR"
else
    missing "Gate 01+ · 正典 function 指针可解析" \
            "摸不到 Python 源目录 —— 在 ci.toml 里写 python_src_dir"
fi

# ══ 架构不变量 1+2 · kernel 零依赖 ════════════════════════════════════════
if [ -n "$PKG" ] && [ -d "$PKG" ]; then
    must_fail "自检 · 零依赖闸门抓得到 kernel 里的第三方 import" \
              "kernel 引入了" \
              bash tools/ci/check_kernel_purity.sh "$BAD/purity"
    step "架构不变量 1+2 · kernel 零依赖" \
         bash tools/ci/check_kernel_purity.sh "$PKG"
elif [ -d "$SRCDIR" ]; then
    missing "架构不变量 1+2 · kernel 零依赖" \
            "有 Python 树却摸不到包目录 —— 在 ci.toml 里写 python_package_dir"
else
    pending "架构不变量 1+2 · kernel 零依赖" \
            "还没有 Python 源码树（阶段 03 之前正常）"
fi

# ══ 架构不变量 3 · 生成表与正典无漂移 ═════════════════════════════════════
# 这一步只对【有生成表】的项目适用。写死一句 `python3 tools/build/codegen_data.py`
# 的版本在没有那个文件的项目上每次都红，而恒红与恒绿一样没有信息量。
if [ -f tools/build/codegen_data.py ]; then
    step "架构不变量 3 · 生成表与正典无漂移" \
         python3 tools/build/codegen_data.py --check
else
    pending "架构不变量 3 · 生成表与正典无漂移" \
            "本项目没有 tools/build/codegen_data.py —— 正典之外没有生成表，无表可漂"
fi

# ══ Gate 03 · 全部测试 ════════════════════════════════════════════════════
step "全部测试" \
     python3 -m pytest -q --no-header -x

step "Gate 02 · 五层验证充分性" \
     python3 tools/ci/check_sufficiency.py

# ══ Gate 05 · 对等测试 / 跨语言 conformance ═══════════════════════════════
if [ -n "$PKG" ] && [ -d "$PKG" ] && [ -n "$KIT" ] && [ -d "$KIT" ]; then
    must_fail "自检 · 对等测试抓得到只存在于 Python 侧的公开名" \
              "在 Swift 侧找不到" \
              python3 tools/ci/check_port_coverage.py \
                      --python "$BAD/port/py" --swift "$BAD/port/swift"
    step "Gate 05 · 对等测试（清单自动探索，五层全查）" \
         python3 tools/ci/check_port_coverage.py --python "$PKG" --swift "$KIT"
elif [ -d swift/Sources ]; then
    missing "Gate 05 · 对等测试" \
            "有 swift/Sources 却摸不到核心库目录 —— 在 ci.toml 里写 swift_kit_dir"
else
    pending "Gate 05 · 对等测试" "还没有 swift/Sources（阶段 05 之前正常）"
fi

# 自己会判「尚不适用」（没有 Package.swift / 这台机器没有 swift），所以走三态。
gate "Gate 05 · 跨语言 conformance" \
     bash tools/ci/check_conformance.sh .

# ══ Gate 06 · 法律隔离 ════════════════════════════════════════════════════
# 三道防线里的第二道。第一道是正典的 strip_on_ship（上面那一步），第三道是
# 对成品抽字符串（Gate S 的 S-4）。三道都要有，因为泄漏的路径不止一条。
if [ -n "$APP" ] && [ -d "$APP" ]; then
    must_fail "自检 · 法律隔离抓得到界面字面量里的式号" \
              "出现教材标识" \
              bash tools/ci/check_legal_isolation.sh "$BAD/legal"
    step "Gate 06 · 法律隔离 · 界面源码（含界面不持有物理）" \
         bash tools/ci/check_legal_isolation.sh "$APP"
    # 出货面比界面层大：出货正典副本与核心库里的字符串常量一样会进二进制。
    # 这里只查教材标识——kernel 当然持有物理，那是它的职责。
    #
    # Python 包算不算出货面，**取决于这个项目有没有桌面前端**，不能一概而论：
    #
    #   * 有 PyInstaller spec ⇒ .pyc 连同 docstring 一起进安装包，是出货面；
    #   * 没有 ⇒ Python 侧只是验证宿主。它的 docstring 里写满【精确到式号的
    #     citation】，而那是规范阶段 01 明文要求的维护依据，不是泄漏。
    #
    # 无条件把它列进来，在后一类项目上一次报四百行（StructureMechOne 实测
    # 405 行，全部是 kernel/composition 的出处注解）——而一个会乱叫的闸门
    # 两天之内就会被关掉。判据用真实产物（*.spec），不用一把新的配置键。
    ISO_TARGETS=()
    [ -f "$SHIPPED" ] && ISO_TARGETS+=("$SHIPPED")
    [ -n "$KIT" ] && [ -d "$KIT" ] && ISO_TARGETS+=("$KIT")
    PYSPEC="$(find . -maxdepth 2 -name "*.spec" 2>/dev/null | head -1)"
    [ -n "$PYSPEC" ] && [ -n "$PKG" ] && [ -d "$PKG" ] && ISO_TARGETS+=("$PKG")
    if [ "${#ISO_TARGETS[@]}" -gt 0 ]; then
        step "Gate 06 · 法律隔离 · 出货面（只查教材标识）" \
             bash tools/ci/check_legal_isolation.sh --identifiers-only "${ISO_TARGETS[@]}"
        [ -n "$PYSPEC" ] || echo "  （${PKG:-Python 包} 未列入：没有 PyInstaller spec，" \
                                 "Python 侧不出货；docstring 里的 citation 是维护依据）"
    fi
elif [ -d swift/Sources ]; then
    missing "Gate 06 · 法律隔离" \
            "有 swift/Sources 却摸不到界面层目录 —— 在 ci.toml 里写 swift_app_dir"
else
    pending "Gate 06 · 法律隔离" "界面层尚未开始（阶段 06 之前正常）"
fi

# ══ Gate S · 出货二进制卫生 ═══════════════════════════════════════════════
# 跑两次：S-1..3 只查得到源码，S-4..6 只查得到成品包。跑一次就报
# 「Gate S 通过」，是对一半的检查说的。
if [ -d swift/Sources ]; then
    step "Gate S · 二进制卫生 · 源码面（S-1..3）" \
         bash tools/ci/check_binary_hygiene.sh swift/Sources
elif [ -n "$PKG" ] && [ -d "$PKG" ]; then
    step "Gate S · 二进制卫生 · 源码面（S-1..3）" \
         bash tools/ci/check_binary_hygiene.sh "$PKG"
fi

FOUND_PACKAGE=false
for _b in ${CI_APP_BUNDLES:-} dist/*.pkg dist/*.ipa; do
    [ -e "$_b" ] || continue
    FOUND_PACKAGE=true
    step "Gate S · 二进制卫生 · $(basename "$_b")（S-4..6）" \
         bash tools/ci/check_binary_hygiene.sh "$_b"
done
if ! $FOUND_PACKAGE; then
    for _b in dist/*.app; do
        [ -d "$_b" ] || continue
        FOUND_PACKAGE=true
        step "Gate S · 二进制卫生 · $(basename "$_b")（S-4..6）" \
             bash tools/ci/check_binary_hygiene.sh "$_b"
    done
fi
$FOUND_PACKAGE || pending "Gate S · 二进制卫生 · 成品面" \
                          "dist/ 里还没有包（阶段 08 之前正常）"

# ══ Gate 07 · 手册、文案、截图、站点 ══════════════════════════════════════
step "自检 · 手册与站点零标识闸门抓得到已知不合格样本" \
     python3 tools/ci/check_manual_isolation.py --self-test
gate "Gate 07 · 两册手册与站点全文零教材标识" \
     python3 tools/ci/check_manual_isolation.py --root .

if [ -f "$LISTING" ]; then
    must_fail "自检 · 文案字数抓得到超长副标题" \
              "超出" \
              python3 tools/ci/check_listing_limits.py "$BAD/LISTING.md"
    gate "Gate 07 · 文案字数与命名规则" \
         python3 tools/ci/check_listing_limits.py "$LISTING"
else
    pending "Gate 07 · 文案字数" "还没有 $LISTING（阶段 07 之前正常）"
fi

if [ -d "$SHOTS" ]; then
    must_fail "自检 · 截图尺寸抓得到不在 ASC 实测档位的图" \
              "不在 ASC 实测接受的尺寸内" \
              python3 tools/ci/check_screenshots.py "$BAD/shots"
    step "Gate 07 · 截图尺寸（ASC 实测值）" \
         python3 tools/ci/check_screenshots.py "$SHOTS"
else
    pending "Gate 07 · 截图尺寸" "还没有 $SHOTS（阶段 07 之前正常）"
fi

# 站点 URL 要联网实测。没有 slug 就没有合理的默认值——猜一个会让这道闸门
# 去查【别人的】站点然后报绿，那比不查更糟。
if [ -n "$SLUG" ]; then
    step "Gate 07 · 站点五个 URL 实测回 200" \
         bash tools/ci/check_urls.sh "$SLUG"
else
    missing "Gate 07 · 站点 URL 实测" "ci.toml 里没有 slug —— 站点隔间名没有合理的默认值"
fi

echo
echo "════════════════════════════════════════════"
printf "通过 %d · 未通过 %d · 尚未到达 %d\n" "$PASS" "$FAIL" "$SKIP"
if [ "$FAIL" -gt 0 ]; then
    echo "${RED}未通过：${FAILED_NAMES[*]}${OFF}"
    echo "闸门不通过就不进下一阶段。"
fi
exit $(( FAIL > 0 ))

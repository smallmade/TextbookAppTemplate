#!/bin/bash
# 每一道闸门，一条命令。
#
#   bash run_all.sh <项目目录>
#
# 标题不写闸门的数目。上一版写的是「十二项」，而那时它已经在跑十三道了 ——
# 一个手写的计数只要跟着别的东西一起改，就会漂，而漂掉的那一刻没有任何
# 东西会失败。数目由末尾的统计说，那个是数出来的。
#
# 「把纪律变成机器的默认行为」——这是缩短开发周期回报最高的单项投入。
# 不适用的检查会跳过并说明为什么，不会假装通过：一道静默放行的闸门比没有
# 闸门更糟，因为没有闸门时你至少知道自己没检查。
set -uo pipefail
P="$(cd "${1:-.}" && pwd)"
CI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; BOLD=$'\033[1m'; OFF=$'\033[0m'

PASS=0; FAILED=0; SKIP=0; FAILED_NAMES=()

# ══════════════════════════════════════════════════════════════
# 项目形状：读 <项目根>/ci.toml，读不到就自动探测。
#
# 这一段之前是 `find "$P/src" -maxdepth 1 -type d | head -1`。它假设
# 扁平布局，而 MechanicsOne 的包在 python/src/mechanicskit，于是【零依赖
# 纪律】【对等测试】【画面图形覆盖】三道全被印成一行黄色的「尚未开始」，
# 而三件事早就做完了。一道按别人的目录形状找不到东西、于是宣布自己不适用
# 的闸门，与一道通过了的闸门，在日志里长得一模一样。
#
# 摸不到就是【未通过】，不是「干净」——见下面 CFG_FAIL 的用法。
# ══════════════════════════════════════════════════════════════
eval "$(python3 "$CI/ci_config.py" --root "$P" --shell)"
CI_PYTHON_PACKAGE_DIR="${CI_PYTHON_PACKAGE_DIR:-}"
CI_SWIFT_APP_DIR="${CI_SWIFT_APP_DIR:-}"
CI_SWIFT_KIT_DIR="${CI_SWIFT_KIT_DIR:-}"
CI_SLUG="${CI_SLUG:-}"
CI_SITE_DIR="${CI_SITE_DIR:-site}"
CI_CONFIG_SOURCE="${CI_CONFIG_SOURCE:-}"

abs() { [ -n "${1:-}" ] && echo "$P/$1" || echo ""; }

# 一道闸门要查的东西根本不在 —— 这不是跳过。
# 「没有东西可查」与「查过了是干净的」必须分得开（架构不变量 6）。
missing() {
    printf "%-26s %-10s ${RED}未通过${OFF}  %s\n" "$1" "$2" "$3"
    FAILED=$((FAILED+1)); FAILED_NAMES+=("$1")
}

#: 退出码 2 的正当理由必须长这个样子。见 run()。
NA_PREFIX='(尚)?不适用|not applicable|NOT_APPLICABLE'
#: argparse 的「参数用法错误」也是退出码 2。它不是「本阶段不适用」。
ARGPARSE='(^|[^A-Za-z])(usage:|error:)|the following arguments are required|unrecognized arguments|invalid choice|expected one argument'

run() {   # run <名称> <闸门> <命令...>
    #
    # 退出码约定：0 = 通过，1 = 未通过，2 = 本阶段尚不适用（跳过）。
    # 第三种是必要的：一道在内容还没写时就报「通过」的闸门是静默放行，
    # 它会让人以为这一项已经查过了。
    #
    # **但退出码 2 已经被 argparse 占用了。** `check_site.py` 把 --slug 改成
    # 必填之后，本 runner 没跟着传，argparse 以 exit 2 退出，于是一个
    # 「参数写错了」被印成一行正常的跳过，理由栏里是 argparse 的报错原文。
    # 它影响共用这份模板的每一款 App，而且正是本文件开头警告的那种静默放行。
    #
    # 所以退出码 2 现在要过两道关：
    #   1. 输出里不得有 argparse 的特征（usage: / error: / 缺参数）；
    #   2. 必须打印本工具约定的「尚不适用」前缀，说出为什么。
    # 两者任一不满足，一律判未通过。
    local name="$1" gate="$2"; shift 2
    printf "%-26s %-10s " "$name" "$gate"
    out="$("$@" 2>&1)"; local code=$?
    # 对象计数：闸门自报「本次检查了几个对象」。N==0 即未通过（不变量 6）。
    local n=""
    n="$(echo "$out" | sed -nE 's/.*CHECKED n=([0-9]+).*/\1/p' | tail -1)"
    local shown=""
    [ -n "$n" ] && shown="  ${n} 个对象"
    case $code in
        0) if [ "${n:-1}" = "0" ]; then
               echo "${RED}未通过${OFF}  报了通过，却一个对象都没检查"
               echo "      「没有东西可查」不是「查过了是干净的」。" | sed 's/^/  /'
               FAILED=$((FAILED+1)); FAILED_NAMES+=("$name")
           else
               echo "${GREEN}通过${OFF}$shown"; PASS=$((PASS+1))
           fi ;;
        2) if echo "$out" | grep -qE "$ARGPARSE"; then
               echo "${RED}未通过${OFF}  退出码 2 来自参数用法错误，不是「不适用」"
               echo "$out" | grep -E "$ARGPARSE" | head -3 | sed 's/^/      /'
               FAILED=$((FAILED+1)); FAILED_NAMES+=("$name")
               return
           fi
           reason="$(echo "$out" | grep -oE "($NA_PREFIX).*" | head -1)"
           if [ -z "$reason" ]; then
               echo "${RED}未通过${OFF}  退出 2 却没有说「尚不适用」以及为什么"
               echo "$out" | grep -v '^[[:space:]]*$' | tail -2 | sed 's/^/      /'
               FAILED=$((FAILED+1)); FAILED_NAMES+=("$name")
           else
               echo "${YELLOW}跳过${OFF}  $reason"
               SKIP=$((SKIP+1))
           fi ;;
        *) echo "${RED}未通过${OFF}$shown"; FAILED=$((FAILED+1)); FAILED_NAMES+=("$name")
           echo "$out" | grep -E "✗|错误|error" | head -4 | sed 's/^/      /' ;;
    esac
}
skip() { printf "%-26s %-10s ${YELLOW}跳过${OFF}  %s\n" "$1" "$2" "$3"; SKIP=$((SKIP+1)); }

echo
echo "${BOLD}闸门总览 · $P${OFF}"
if [ -n "$CI_CONFIG_SOURCE" ]; then
    echo "  形状读自 ci.toml"
else
    echo "  ${YELLOW}没有 ci.toml —— 目录形状靠自动探测${OFF}"
fi
echo

SPEC="$P/spec/specification.json"
[ -f "$SPEC" ] && run "正典" "Gate 01" python3 "$CI/check_spec.py" "$SPEC" \
                || skip "正典" "Gate 01" "没有 spec/specification.json"

PKG="$(abs "$CI_PYTHON_PACKAGE_DIR")"
if [ -n "$PKG" ] && [ -d "$PKG" ]; then
    run "零依赖纪律" "不变量1,2" bash "$CI/check_kernel_purity.sh" "$PKG"
elif [ -d "$P/src" ] || [ -d "$P/python" ]; then
    missing "零依赖纪律" "不变量1,2" \
            "有 Python 树却摸不到包目录 —— 在 ci.toml 里写 python_package_dir"
else
    skip "零依赖纪律" "不变量1,2" "尚不适用：还没有 Python 源码树（阶段 03 之前正常）"
fi

run "充分性判据" "Gate 02" python3 "$CI/check_sufficiency.py" "$P"
run "输入格式矩阵" "Gate 02" python3 "$CI/check_input_matrix.py" "$P"
run "引用页码核对" "Gate 02" python3 "$CI/check_citations.py" --root "$P"
run "适配审计" "Gate 04" python3 "$CI/check_coverage_audit.py" "$P"

SWIFT="$(abs "$CI_SWIFT_KIT_DIR")"
if [ -n "$PKG" ] && [ -d "$PKG" ] && [ -n "$SWIFT" ] && [ -d "$SWIFT" ]; then
    run "对等测试" "Gate 05" python3 "$CI/check_port_coverage.py" --python "$PKG" --swift "$SWIFT"
elif [ -d "$P/swift/Sources" ]; then
    missing "对等测试" "Gate 05" \
            "有 swift/Sources 却摸不到核心库目录 —— 在 ci.toml 里写 swift_kit_dir"
else
    skip "对等测试" "Gate 05" "尚不适用：Swift 侧尚未开始（阶段 05 之前正常）"
fi

run "跨语言 conformance" "Gate 05" bash "$CI/check_conformance.sh" "$P"

APPDIR="$(abs "$CI_SWIFT_APP_DIR")"
if [ -n "$APPDIR" ] && [ -d "$APPDIR" ]; then
    run "画面图形覆盖" "Gate 06" python3 "$CI/check_figures.py" --root "$P"
    run "画面可达性" "Gate 04" python3 "$CI/check_screen_reachability.py" --root "$P"
    run "界面走查记录" "Gate 06" python3 "$CI/check_interface_review.py" --root "$P"
    run "界面字串" "Gate 06A" python3 "$CI/check_ui_strings.py" --root "$P"
    run "原生对标" "Gate 06A" python3 "$CI/check_native_parity.py" --root "$P"
    run "分支可见" "Gate M1" python3 "$CI/check_branching_visible.py" --root "$P"
    run "法律隔离" "Gate 06" bash "$CI/check_legal_isolation.sh" "$APPDIR"
    run "手册进包" "Gate 07" python3 "$CI/check_help_bundled.py" --root "$P"
    run "设备矩阵" "Gate 06B" python3 "$CI/check_device_matrix.py" --root "$P"
    run "App 图标" "Gate M7" python3 "$CI/check_icon.py" --root "$P"
elif [ -d "$P/swift/Sources" ]; then
    missing "界面层各闸门" "Gate 06" \
            "有 swift/Sources 却摸不到界面层目录 —— 在 ci.toml 里写 swift_app_dir"
else
    skip "界面层各闸门" "Gate 06" "尚不适用：界面层尚未开始（阶段 06 之前正常）"
fi

run "测试文件非空" "Gate 03" python3 "$CI/check_test_files.py" --root "$P"
run "未覆盖分支说明" "Gate 03" python3 "$CI/check_coverage_gaps.py" --root "$P"
run "正典公式渲染覆盖" "Gate 06" python3 "$CI/check_formula_coverage.py" --root "$P"
run "手册覆盖" "Gate 07" python3 "$CI/check_manual_coverage.py" --root "$P"
run "手册与站点零标识" "Gate 07" python3 "$CI/check_manual_isolation.py" --root "$P"
run "闸门接线（元闸门）" "Gate 00" python3 "$CI/check_gates_are_wired.py" --root "$P"
# [M-03] 无漂移比对本来没被通用 runner 调用过，而姊妹项目的 runner 里给它
# 写的跳过理由是「依赖另一款的 design/prototype.html」——通读脚本全文，
# 它一次也不提那个文件。一句没人核对过的跳过理由，效果等同于关掉闸门。
run "工具链单一真身" "不变量6" bash "$CI/check_no_drift.sh" "$(dirname "$P")" --mine "$(basename "$P")"

LISTING="$P/submission/LISTING.md"
[ -f "$LISTING" ] && run "文案字数" "Gate 07" python3 "$CI/check_listing_limits.py" "$LISTING" \
                  || skip "文案字数" "Gate 07" "尚不适用：没有 submission/LISTING.md"

run "层 5 裁定纪律" "Gate 02" python3 "$CI/check_layer5.py" --root "$P"

# 打包一致性：只有当 PyInstaller spec 与 Inno 脚本都存在时才适用（阶段 09）。
# 一道条件不具备就跳过、并说出为什么的闸门，好过一道不在清单里的闸门——
# 后者会安静地不存在。
PLAIN="$(find "$P" -maxdepth 2 -name "*.spec" 2>/dev/null | head -1)"
INNO="$(find "$P" -maxdepth 3 -name "*.iss" 2>/dev/null | head -1)"
if [ -n "$PLAIN" ] && [ -n "$INNO" ] && [ -n "${CI_STORE_BUNDLE_ID:-}" ]; then
    # [M-03] bundle id 曾经写死成 "com.smallmade.structuremechone" ——
    # 又一处「按另一款 App 写死」。现在从 ci.toml 读；没声明就是未通过，
    # 因为拿别人的 bundle id 去比对，比对的是别人。
    run "打包一致性" "Gate 09" python3 "$CI/check_packaging.py" \
        --plain-spec "$PLAIN" --qt-spec "$PLAIN" --inno "$INNO" \
        --store-bundle-id "$CI_STORE_BUNDLE_ID"
elif [ -n "$PLAIN" ] && [ -n "$INNO" ]; then
    missing "打包一致性" "Gate 09" "ci.toml 里没有 store_bundle_id —— 别人的 bundle id 比对的是别人"
else
    skip "打包一致性" "Gate 09" "尚不适用：还没有 PyInstaller spec 与 Inno 脚本（阶段 09）"
fi

# [M-03] --slug 是必填的，而这里从来没传过：argparse 以退出码 2 退出，
# 上一版的 run() 把它当成「本阶段尚不适用」印成一行黄色的跳过，理由栏里
# 是 argparse 的报错原文。值从 ci.toml 读；读不到就是未通过，不是跳过——
# 一个猜出来的 slug 会让末尾印出的五个 URL 指向别人的站点。
if [ -n "$CI_SLUG" ]; then
    run "站点本地检查" "Gate 07" python3 "$CI/check_site.py" "$P/$CI_SITE_DIR" --slug "$CI_SLUG"
elif [ -d "$P/$CI_SITE_DIR" ]; then
    missing "站点本地检查" "Gate 07" "ci.toml 里没有 slug —— 站点隔间名没有合理的默认值"
else
    skip "站点本地检查" "Gate 07" "尚不适用：还没有站点目录（阶段 07 之前正常）"
fi

SHOTS="$P/submission/screenshots"
[ -d "$SHOTS" ] && run "截图尺寸" "Gate 07" python3 "$CI/check_screenshots.py" "$SHOTS" \
                || skip "截图尺寸" "Gate 07" "尚不适用：还没有截图"

run "plist 纪律" "Gate 08" bash "$CI/check_plists.sh" "$P"
run "构建号台账" "Gate 08" python3 "$CI/check_ledger.py" "$P"

# Gate S 要跑两次，因为它的六项分在两边：S-1..3 只能对源码查，S-4..6 只能
# 对成品包查。跑一次就报「Gate S 通过」，是对一半的检查说的。
if [ -d "$P/swift/Sources" ]; then
    run "二进制卫生·源码" "Gate S" bash "$CI/check_binary_hygiene.sh" "$P/swift/Sources"
elif [ -n "$PKG" ]; then
    run "二进制卫生·源码" "Gate S" bash "$CI/check_binary_hygiene.sh" "$PKG"
fi

FOUND_PACKAGE=false
# ci.toml 可以点名成品在哪（构建产物未必在 dist/：MechanicsOne 的两个
# bundle 在 build/）。点了名的先扫，扫完再看 dist/。
for named in ${CI_APP_BUNDLES:-}; do
    [ -e "$P/$named" ] || continue
    FOUND_PACKAGE=true
    run "二进制卫生 $(basename "$named")" "Gate S" bash "$CI/check_binary_hygiene.sh" "$P/$named"
done
for pkgfile in "$P"/dist/*.pkg "$P"/dist/*.ipa; do
    [ -f "$pkgfile" ] || continue
    FOUND_PACKAGE=true
    run "二进制卫生 $(basename "$pkgfile")" "Gate S" bash "$CI/check_binary_hygiene.sh" "$pkgfile"
done
# .app 也查。规范说要对着 .pkg / .ipa，而那要等阶段 08 打包；在那之前对
# .app 查 S-4..6 已经能抓到全部三类问题，而【等到打包才查】意味着这道闸门
# 在整个阶段 06 里一次也没跑过。
if ! $FOUND_PACKAGE; then
    for appdir in "$P"/dist/*.app; do
        [ -d "$appdir" ] || continue
        FOUND_PACKAGE=true
        run "二进制卫生 $(basename "$appdir")" "Gate S" bash "$CI/check_binary_hygiene.sh" "$appdir"
    done
fi
$FOUND_PACKAGE || skip "二进制卫生·成品" "Gate S" "尚不适用：dist/ 里还没有包（阶段 08 之前正常）"

# —— 出货副本：剥离 → 两道独立复查 ——
#
# 这一段来自热力学项目的会话。剥离脚本自己说「剥完了」不算数，所以剥完之后
# 有两道方向不同的复查：check_spec --shipped 查【字段】是否剥净，
# check_ship_isolation 查【内容】里还有没有标识残留。
# 字段剥干净不等于内容剥干净——作者姓氏留在 sources[].key 里就是实例。
SHIP="$P/build/specification.ship.json"
if [ -f "$SPEC" ]; then
    if python3 "$CI/strip_spec.py" "$SPEC" "$SHIP" >/dev/null 2>&1; then
        run "出货副本·字段" "Gate 01" python3 "$CI/check_spec.py" "$SHIP" --shipped
        run "出货副本·内容" "Gate 06" python3 "$CI/check_ship_isolation.py" "$SHIP" --dev "$SPEC"
    else
        skip "出货副本" "Gate 01/06" "剥离脚本未通过自检 —— 单独跑 strip_spec.py 看原因"
    fi
else
    skip "出货副本" "Gate 01/06" "没有正典"
fi

# ══════════════════════════════════════════════════════════════
# 元闸门要求 tools/ci 里每一道 check_* 都被【本项目的】runner 调用。
# 下面这八道以前只有 run_all_local.sh（MechanicsOne 形状）在跑，通用 runner
# 一道都没提——于是用通用 runner 的项目里，它们既没执行、也没出现在日志里。
# 一道没人调用的闸门与一道通过了的闸门，在日志里长得一模一样。
#
# 路径一律走 ci.toml。写死任何一款的目录形状，是这些脚本分叉成两份的成因。
# ══════════════════════════════════════════════════════════════

CI_ENTITLEMENTS="${CI_ENTITLEMENTS:-}"
CI_TESTS_DIR="${CI_TESTS_DIR:-}"

run "正典 function 指针" "Gate 01" python3 "$CI/check_canon_functions.py" \
    "$SPEC" --root "$P"

run "理论手册散文源" "Gate 07" python3 "$CI/check_theory.py" --root "$P"

run "施工书台账" "Gate 00" python3 "$CI/check_plan.py" --root "$P"

run "层 3 符号证明真的被执行" "Gate 02" python3 "$CI/check_layer3_symbolic.py" \
    --root "$P"

run "第二源声明与层 5 fixture 对得上" "Gate 02" \
    python3 "$CI/check_second_source.py" --root "$P"

APPDIR="$(abs "$CI_SWIFT_APP_DIR")"
KITDIR="$(abs "$CI_SWIFT_KIT_DIR")"
if [ -n "$CI_SWIFT_APP_DIR" ] && [ -d "$APPDIR" ]; then
    run "不变量 4 · 出货源码不依赖包外输入" "不变量4" \
        bash "$CI/check_app_purity.sh" "$APPDIR" ${KITDIR:+"$KITDIR"}
else
    missing "出货源码纯度" "不变量4" "ci.toml 没有声明 swift_app_dir，或它不存在"
fi

ENT="$(abs "$CI_ENTITLEMENTS")"
if [ -n "$CI_ENTITLEMENTS" ] && [ -f "$ENT" ] && [ -d "$APPDIR" ]; then
    run "entitlements 与代码里在用的 API 对得上" "Gate 08" \
        python3 "$CI/check_entitlements.py" "$ENT" "$APPDIR"
else
    skip "entitlements 一致性" "Gate 08" \
         "尚不适用：ci.toml 没有声明 entitlements（阶段 08 之前正常）"
fi

if [ -n "$CI_SLUG" ]; then
    run "站点五个 URL 实测回 200" "Gate 07" bash "$CI/check_urls.sh" "$CI_SLUG"
else
    missing "站点 URL 实测" "Gate 07" "ci.toml 没有声明 slug"
fi

run "许可审计" "Gate 09" python3 "$CI/audit_licences.py" "$P/dist"

echo
echo "${BOLD}通过 $PASS   未通过 $FAILED   跳过 $SKIP${OFF}"
if [ "$FAILED" -gt 0 ]; then
    echo "${RED}未通过：${FAILED_NAMES[*]}${OFF}"; echo; exit 1
fi
echo "${GREEN}全部通过（跳过的是本阶段尚不适用的）。${OFF}"; echo; exit 0

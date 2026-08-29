#!/bin/bash
# 十二项闸门，一条命令。
#
#   bash run_all.sh <项目目录>
#
# 「把纪律变成机器的默认行为」——这是缩短开发周期回报最高的单项投入。
# 不适用的检查会跳过并说明为什么，不会假装通过：一道静默放行的闸门比没有
# 闸门更糟，因为没有闸门时你至少知道自己没检查。
set -uo pipefail
P="$(cd "${1:-.}" && pwd)"
CI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; BOLD=$'\033[1m'; OFF=$'\033[0m'

PASS=0; FAILED=0; SKIP=0; FAILED_NAMES=()

run() {   # run <名称> <闸门> <命令...>
    #
    # 退出码约定：0 = 通过，1 = 未通过，2 = 本阶段尚不适用（跳过）。
    # 第三种是必要的：一道在内容还没写时就报「通过」的闸门是静默放行，
    # 它会让人以为这一项已经查过了。
    local name="$1" gate="$2"; shift 2
    printf "%-26s %-10s " "$name" "$gate"
    out="$("$@" 2>&1)"; local code=$?
    case $code in
        0) echo "${GREEN}通过${OFF}"; PASS=$((PASS+1)) ;;
        2) echo "${YELLOW}跳过${OFF}  $(echo "$out" | grep -oE '尚不适用.*' | head -1)"
           SKIP=$((SKIP+1)) ;;
        *) echo "${RED}未通过${OFF}"; FAILED=$((FAILED+1)); FAILED_NAMES+=("$name")
           echo "$out" | grep -E "✗|错误|error" | head -4 | sed 's/^/      /' ;;
    esac
}
skip() { printf "%-26s %-10s ${YELLOW}跳过${OFF}  %s\n" "$1" "$2" "$3"; SKIP=$((SKIP+1)); }

echo
echo "${BOLD}十二项闸门 · $P${OFF}"
echo

SPEC="$P/spec/specification.json"
[ -f "$SPEC" ] && run "正典" "Gate 01" python3 "$CI/check_spec.py" "$SPEC" \
                || skip "正典" "Gate 01" "没有 spec/specification.json"

PKG="$(find "$P/src" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | head -1)"
[ -n "$PKG" ] && run "零依赖纪律" "不变量1,2" bash "$CI/check_kernel_purity.sh" "$PKG" \
              || skip "零依赖纪律" "不变量1,2" "没有 src/<包>"

run "充分性判据" "Gate 02" python3 "$CI/check_sufficiency.py" "$P"
run "输入格式矩阵" "Gate 02" python3 "$CI/check_input_matrix.py" "$P"

SWIFT="$(find "$P/swift/Sources" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | grep -v App | grep -v Verify | head -1)"
if [ -n "$PKG" ] && [ -n "$SWIFT" ]; then
    run "对等测试" "Gate 05" python3 "$CI/check_port_coverage.py" --python "$PKG" --swift "$SWIFT"
else
    skip "对等测试" "Gate 05" "Swift 侧尚未开始（阶段 05 之前正常）"
fi

APPDIR="$(find "$P/swift/Sources" -maxdepth 1 -type d -name "*App" 2>/dev/null | head -1)"
[ -n "$APPDIR" ] && run "法律隔离" "Gate 06" bash "$CI/check_legal_isolation.sh" "$APPDIR" \
                 || skip "法律隔离" "Gate 06" "界面层尚未开始（阶段 06 之前正常）"

LISTING="$P/submission/LISTING.md"
[ -f "$LISTING" ] && run "文案字数" "Gate 07" python3 "$CI/check_listing_limits.py" "$LISTING" \
                  || skip "文案字数" "Gate 07" "没有 submission/LISTING.md"

SHOTS="$P/submission/screenshots"
[ -d "$SHOTS" ] && run "截图尺寸" "Gate 07" python3 "$CI/check_screenshots.py" "$SHOTS" \
                || skip "截图尺寸" "Gate 07" "还没有截图"

run "plist 纪律" "Gate 08" bash "$CI/check_plists.sh" "$P"

for pkgfile in "$P"/dist/*.pkg "$P"/dist/*.ipa; do
    [ -f "$pkgfile" ] || continue
    run "二进制卫生 $(basename "$pkgfile")" "Gate S" bash "$CI/check_binary_hygiene.sh" "$pkgfile"
done
ls "$P"/dist/*.pkg "$P"/dist/*.ipa >/dev/null 2>&1 || \
    skip "二进制卫生" "Gate S" "dist/ 里还没有包（阶段 08 之前正常）"

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

run "许可审计" "Gate 09" python3 "$CI/audit_licences.py" "$P/dist"

echo
echo "${BOLD}通过 $PASS   未通过 $FAILED   跳过 $SKIP${OFF}"
if [ "$FAILED" -gt 0 ]; then
    echo "${RED}未通过：${FAILED_NAMES[*]}${OFF}"; echo; exit 1
fi
echo "${GREEN}全部通过（跳过的是本阶段尚不适用的）。${OFF}"; echo; exit 0

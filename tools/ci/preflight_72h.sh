#!/bin/bash
# 提交前 72 小时 · 一条命令跑完能自动化的部分
#
#   bash tools/ci/preflight_72h.sh <项目目录> [--offline]
#
# 规范第三部分把上架从「一堆零散动作」变成一条固定流程，每一项都对应一次
# 真实失败。这个脚本把其中**能自动化的**跑掉，并把**不能自动化的**逐条打
# 印出来——后者才是它最重要的输出。
#
# 一道声称「全部通过」而其实有三件事没查的检查，比没有检查更糟：它把
# 「我没查」变成了「查过了，没问题」。所以这里的人工项不是附注，是清单的
# 一部分，而且脚本的退出码不会因为它们被忽略而变绿。
#
# --offline 跳过需要网络的一项（站点 URL）。
set -uo pipefail
P="${1:-.}"; shift 2>/dev/null || true
OFFLINE=0
for a in "$@"; do [ "$a" = "--offline" ] && OFFLINE=1; done
cd "$P" || exit 1
P="$PWD"

RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'
BOLD=$'\033[1m'; DIM=$'\033[2m'; OFF=$'\033[0m'
PY="${PYTHON:-python3}"
SLUG=structuremechone
FAILED=0; FAILED_NAMES=()

step() {  # step <T 段> <名称> <命令...>
    local when="$1" name="$2"; shift 2
    printf "  %-7s %-30s " "$when" "$name"
    out="$("$@" 2>&1)"; local code=$?
    case $code in
        0) echo "${GREEN}通过${OFF}" ;;
        2) echo "${YELLOW}跳过${OFF}  $(echo "$out" | grep -oE '(尚)?不适用.*' | head -1)" ;;
        *) echo "${RED}未通过${OFF}"; FAILED=$((FAILED+1)); FAILED_NAMES+=("$name")
           echo "$out" | grep -E "✗|未通过|错误|error" | head -4 | sed 's/^/            /' ;;
    esac
}

echo
echo "${BOLD}提交前 72 小时 · $P${OFF}"
echo

# ── T−72h ────────────────────────────────────────────────────────────
echo "${DIM}T−72h  成品本身${OFF}"
step "T−72h" "全部闸门" bash tools/ci/run_all.sh
for app in dist/*.app; do
    [ -e "$app" ] || continue
    step "T−72h" "二进制卫生 $(basename "$app")" \
         bash tools/ci/check_binary_hygiene.sh "$app"
done
step "T−72h" "输入格式矩阵" "$PY" tools/ci/check_input_matrix.py .
echo

# ── T−48h ────────────────────────────────────────────────────────────
echo "${DIM}T−48h  商店材料${OFF}"
step "T−48h" "文案字数" "$PY" tools/ci/check_listing_limits.py submission/LISTING.md
step "T−48h" "截图尺寸" "$PY" tools/ci/check_screenshots.py submission/screenshots/
step "T−48h" "站点本地检查" "$PY" tools/ci/check_site.py "$P/site"
if [ "$OFFLINE" -eq 1 ]; then
    printf "  %-7s %-30s ${YELLOW}跳过${OFF}  %s\n" "T−48h" "站点五个 URL" \
           "不适用：--offline"
else
    step "T−48h" "站点五个 URL" bash tools/ci/check_urls.sh "$SLUG"
fi
echo

# ── T−24h ────────────────────────────────────────────────────────────
echo "${DIM}T−24h  打包与签名${OFF}"
step "T−24h" "plist 纪律" bash tools/ci/check_plists.sh "$P"
step "T−24h" "构建号台账" "$PY" tools/ci/check_ledger.py "$P"
echo

# ── 不能自动化的部分 ─────────────────────────────────────────────────
echo "${BOLD}这台机器查不到的，逐条自己查${OFF}"
cat <<'MANUAL'
  T−24h  ASC 的 TestFlight/Builds 页：台账里的下一个号没被占用
  T−24h  验证段三项：sandbox / application-identifier / get-task-allow
         —— 拆开成品包再验一次，不要相信「我记得它是对的」
  T−0    Transporter 投递 → 等处理完成 → 装真机走 RC 清单
  T−0    Gate R-1：确认这是本轮**唯一**在提交的 App
  T−0    Gate R-4：答复审核时陈述**做过的验证**，不要陈述**没有的设备**
MANUAL
echo

if [ "$FAILED" -gt 0 ]; then
    echo "${RED}${BOLD}未通过 $FAILED 项：${FAILED_NAMES[*]}${OFF}"; echo
    exit 1
fi
echo "${GREEN}${BOLD}可自动化的部分全数通过。上面五条人工项仍待确认。${OFF}"
echo
exit 0

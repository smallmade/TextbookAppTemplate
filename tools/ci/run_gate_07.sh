#!/bin/bash
# Gate 07 全项 —— 一条命令跑完。
#
#   bash tools/ci/run_gate_07.sh
#
# 两份手册**都是生成的**，而且都从【剥离过的】正典生成——所以「手册里没有
# 教材标识」不是一条要记得遵守的规则，而是结构上做不到：那些字段根本不在
# 输入里。脚本仍然扫一遍输出，因为泄漏的路径不止一条。
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; BOLD=$'\033[1m'; OFF=$'\033[0m'
FAILED=0
step() {
    local name="$1"; shift
    if "$@" >/tmp/gate07.out 2>&1; then
        echo "  ${GREEN}✓${OFF} $name"
    else
        echo "  ${RED}✗${OFF} $name"; sed 's/^/      /' /tmp/gate07.out | head -12
        FAILED=1
    fi
}

echo "${BOLD}Gate 07 · 双手册与站点${OFF}"
echo
step "剥离出货正典" python3 tools/ci/strip_spec.py spec/specification.json build/specification.shipped.json
step "理论手册（全自动，53 个模块）" python3 tools/manual/build_theory.py
step "使用手册（画面清单从界面源码抽）" python3 tools/manual/build_usage.py
step "站点隔间页（隐私页由清单生成）" python3 tools/manual/build_site.py
step "站点自洽（五页齐备、链接可达、隐私一致）" python3 tools/ci/check_site.py site --slug mechanicsone
step "手册与站点无教材标识" bash tools/ci/check_legal_isolation.sh --identifiers-only site submission
step "商店文案字数与命名规则" python3 tools/ci/check_listing_limits.py submission/LISTING.md

echo
if [ "$FAILED" -eq 0 ]; then
    echo "${GREEN}${BOLD}Gate 07 可自动化的部分全数通过。${OFF}"
    echo
    echo "${YELLOW}仍需人做的两件：${OFF}"
    echo "  1. ${BOLD}截图${OFF} —— 必须由【真实交互】驱动：Release 构建，"
    echo "     像人一样点和输。不许用隐藏开关预设界面——那正是"
    echo "     Guideline 5.6 的触发物，而现在的二进制里也已经没有可用的开关。"
    echo "     ASC 实测尺寸：iPhone 1284×2778（6.9\" 的 1320×2868 会被当场拒收），"
    echo "     iPad 13\" 2064×2752。"
    echo "  2. ${BOLD}部署${OFF} —— 五个 URL 实测回 200。本地只能验到链接自洽。"
    exit 0
fi
echo "${RED}${BOLD}Gate 07 未通过。${OFF}"
exit 1

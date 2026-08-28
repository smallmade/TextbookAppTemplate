#!/bin/bash
# Gate 06 —— 法律隔离：界面层不得出现教材标识，也不得持有物理。
#
#   bash check_legal_isolation.sh <界面源码目录> [资源目录...]
#
# 数学关系是事实与方法，不受著作权保护；受保护的是教材的**表达**——文字、
# 编排、习题题干、图表的具体呈现。所以公式可以显示，「Gere §5.3 Eq.5-12」
# 不可以。后者带来的可信度，用「对照 NIST 数据验证」也能拿到，而且零风险。
#
# 这是三道防线里的第二道。第一道是正典的 strip_on_ship，第三道是对成品
# bundle 抽字符串（check_binary_hygiene.sh）。三道都要有，因为泄漏的路径
# 不止一条。
set -uo pipefail
[ $# -ge 1 ] || { echo "用法: bash check_legal_isolation.sh <界面源码目录> [资源目录...]" >&2; exit 2; }

RED=$'\033[31m'; GREEN=$'\033[32m'; BOLD=$'\033[1m'; OFF=$'\033[0m'
FAIL=0

# 教材作者姓氏。这张表随项目增长——每加一部教材就把姓氏加进来。
AUTHORS='anderson|gere|hibbeler|cengel|moran|incropera|timoshenko|munson|turns|roark'
# 教材的编号体系。这些是「表达」，不是「事实」。
NUMBERING='Eq\.[[:space:]]*[0-9]|Example[[:space:]]+[0-9]|Problem[[:space:]]+[0-9]|Table[[:space:]]+[0-9]+-|Figure[[:space:]]+[0-9]+-|§[[:space:]]*[0-9]'

selftest() {
    local T; T="$(mktemp -d)"
    printf 'let note = "see Gere Eq. 5-12"\n' > "$T/violation.swift"
    printf 'let ok = "verified against NIST reference data"\n' > "$T/clean.swift"
    local caught missed
    caught="$(grep -rnEi "$AUTHORS|$NUMBERING" "$T/violation.swift" 2>/dev/null || true)"
    missed="$(grep -rnEi "$AUTHORS|$NUMBERING" "$T/clean.swift" 2>/dev/null || true)"
    rm -rf "$T"
    [ -n "$caught" ] || { echo "${RED}自检失败：真违规没被抓到，结果不可信${OFF}" >&2; return 1; }
    [ -z "$missed" ]  || { echo "${RED}自检失败：合规文本被误判${OFF}" >&2; return 1; }
    return 0
}
selftest || exit 2

echo
echo "${BOLD}Gate 06 · 法律隔离${OFF}"

echo "${BOLD}教材标识${OFF}"
HITS="$(grep -rnEi "$AUTHORS|$NUMBERING" "$@" 2>/dev/null \
        | grep -vE '^\s*(//|#|\*)' || true)"
if [ -n "$HITS" ]; then
    echo "  ${RED}✗${OFF} 界面层／资源里出现教材标识："
    echo "$HITS" | sed 's/^/      /'
    echo "      → 公式本身可以显示；书名、作者、式号不可以。"
    echo "      → 公有领域来源（NACA / NASA / NIST / IAPWS / CODATA）可以具名，"
    echo "        而且反而增强可信度。"
    FAIL=$((FAIL+1))
else
    echo "  ${GREEN}✓${OFF} 无教材标识"
fi

echo
echo "${BOLD}界面不持有物理${OFF}"
# 界面层里出现多位小数的字面量，通常是把物理常数写进了界面。
# 所有显示决策应当来自共用的 ui 决策层。
CONST="$(grep -rnE '[^0-9a-zA-Z_.][0-9]+\.[0-9]{3,}' "$@" --include="*.swift" 2>/dev/null \
         | grep -vE '^\s*(//|#|\*)|version|Version|[0-9]\.[0-9]+\.[0-9]' || true)"
if [ -n "$CONST" ]; then
    echo "  ${RED}✗${OFF} 界面层出现多位小数常数（物理应留在 ui 决策层）："
    echo "$CONST" | sed 's/^/      /'
    FAIL=$((FAIL+1))
else
    echo "  ${GREEN}✓${OFF} 界面层无物理常数"
fi

echo
[ "$FAIL" -eq 0 ] && { echo "${GREEN}${BOLD}Gate 06 法律隔离通过。${OFF}"; echo; exit 0; }
echo "${RED}${BOLD}未通过：$FAIL 项。${OFF}"; echo; exit 1

#!/bin/bash
# 架构不变量 4（源码级）—— 出货二进制的行为不得依赖包外的任何输入。
#
#   bash check_app_purity.sh swift/Sources/MechanicsOneApp [更多目录...]
#
# 真正的闸门是阶段 S 的 check_binary_hygiene.sh，它对着 .pkg / .ipa 抽字符串。
# 这一道在源码上跑，是为了让问题在**写下的那一刻**就红，而不是等到打包前
# 七十二小时。两道都要有：源码干净不等于二进制干净（资源文件、正典副本、
# 第三方库都可能带进禁用字串），而二进制检查也不会告诉你是哪一行写的。
#
# 这条不变量是 Guideline 5.6 拒审换来的，而 5.6 是【账号层】判定——它一次性
# 影响账号下全部 App。触发它的是一个所有人都会觉得无害的工程习惯：为了自动
# 截图，在出货二进制里留了一个环境变量开关。那个开关预设的每一个状态，用户
# 自己点也到得了；它没有解锁任何功能。**但看二进制的人无从知道这一点。**
set -uo pipefail
[ $# -ge 1 ] || { echo "用法: bash check_app_purity.sh <目录>..." >&2; exit 2; }

RED=$'\033[31m'; GREEN=$'\033[32m'; BOLD=$'\033[1m'; OFF=$'\033[0m'

# 每一条都对应「行为可以被包外的东西改变」的一种路径。
PATTERNS=(
  'ProcessInfo\.processInfo\.environment:读环境变量'
  '\bgetenv\b:读环境变量'
  '\bProcess\(\):派生进程'
  '\bdlopen\b:动态加载'
  'NSClassFromString:按名字取类'
  'CommandLine\.arguments:读命令行参数'
  '/opt/homebrew:包外路径'
  '/usr/local/bin:包外路径'
)

# 闸门必须能自证还活着：一个「没找到问题就算通过」的检查，没有已知会失败的
# 样本就等于没有检查。阶段 S 的第一版脚本因为过滤模式以 `--` 开头，被 grep
# 当成选项报错退出，管线末端的 `|| true` 把错误吞掉，于是它报告「零命中 ✓」。
selftest() {
    local T; T="$(mktemp -d)" || return 1
    printf 'let flag = ProcessInfo.processInfo.environment["QA_MODE"]\n' > "$T/bad.swift"
    printf 'let url = Bundle.module.url(forResource: "spec", withExtension: "json")\n' > "$T/good.swift"
    local caught missed rc=0
    caught="$(grep -rnE 'ProcessInfo\.processInfo\.environment' "$T/bad.swift" 2>/dev/null)"
    missed="$(grep -rnE 'ProcessInfo\.processInfo\.environment' "$T/good.swift" 2>/dev/null)"
    rm -rf "$T"
    [ -n "$caught" ] || { echo "${RED}自检失败：真违规没被抓到${OFF}" >&2; rc=1; }
    [ -z "$missed" ]  || { echo "${RED}自检失败：合规代码被误判${OFF}" >&2; rc=1; }
    return $rc
}
selftest || { echo "${RED}${BOLD}闸门自身不可信，拒绝报告结果。${OFF}" >&2; exit 2; }

echo
echo "${BOLD}架构不变量 4 · 源码级${OFF}"
FAIL=0
for ENTRY in "${PATTERNS[@]}"; do
    PATTERN="${ENTRY%%:*}"; WHY="${ENTRY##*:}"
    HITS="$(grep -rnEI "$PATTERN" "$@" --include="*.swift" 2>/dev/null \
            | grep -vE ':[0-9]+:[[:space:]]*(//|\*)' || true)"
    if [ -n "$HITS" ]; then
        echo "  ${RED}✗${OFF} $WHY："
        echo "$HITS" | sed 's/^/      /'
        FAIL=$((FAIL+1))
    fi
done

if [ "$FAIL" -eq 0 ]; then
    echo "  ${GREEN}✓${OFF} 出货源码不读环境变量、不派生进程、不动态加载、不引用包外路径"
    echo
    exit 0
fi
echo
echo "  ${RED}正确解法不是「留个开关但藏好」，是把需求移出出货二进制：${OFF}"
echo "    · 测试要指向包内 helper → 测试运行目录照抄 .app 的形状"
echo "    · 自动抓商店截图      → 脚本驱动真实交互，不从外部预设内部状态"
echo "    · 开发期调试面板      → #if DEBUG 编译期隔离，Release 里连符号都没有"
echo "${RED}${BOLD}未通过：$FAIL 项。${OFF}"; echo; exit 1

#!/bin/bash
# Gate 06 —— 法律隔离：界面层不得出现教材标识，也不得持有物理。
#
#   bash check_legal_isolation.sh <界面源码目录> [资源目录...]
#
# 数学关系是事实与方法，不受著作权保护；受保护的是教材的**表达**——文字、
# 编排、习题题干、图表的具体呈现。所以公式可以显示，「Gere §5.3 Eq.5-12」
# 不可以。后者带来的可信度，用「对照 NASA / NIST 数据验证」也能拿到，
# 而且零风险。
#
# 这是三道防线里的第二道。第一道是正典的 strip_on_ship，第三道是对成品
# bundle 抽字符串（check_binary_hygiene.sh）。三道都要有，因为泄漏的路径
# 不止一条。
set -uo pipefail
usage() { echo "用法: bash check_legal_isolation.sh [--identifiers-only] <目录|文件>..." >&2; exit 2; }

# 两项检查的适用范围不同，所以要能分开跑：
#   * 教材标识 —— 适用于【全部会出货的东西】。kernel 里的一个字符串常量
#     一样会进二进制，Presentation 的解释句更是直接显示给用户。
#   * 界面不持有物理 —— 只适用于 <Core>App。kernel 当然持有物理，那是它的
#     职责；把这条规则套到 kernel 上，只会得到一份必然全红的报告。
IDENTIFIERS_ONLY=0
if [ "${1-}" = "--identifiers-only" ]; then IDENTIFIERS_ONLY=1; shift; fi
[ $# -ge 1 ] || usage

RED=$'\033[31m'; GREEN=$'\033[32m'; BOLD=$'\033[1m'; OFF=$'\033[0m'
FAIL=0

# 教材作者姓氏 = 【从正典自动导出】 ∪ 一份跨项目防御名单。
#
# 手写名单会漂移，理由和「公开函数清单必须自动探索」是同一条：本项目的
# 受版权来源就写在 spec/specification.json 的 sources 里，让闸门自己去读，
# 加一部教材就不需要有人记得同时改这个脚本。
#
# 防御名单里【故意不含两个姓氏】，理由相同：它们同时是普通英文词。
#
#   * turns —— Stephen Turns 是燃烧学教材的作者，而 `turns` 是 `returns` 的
#     子串，kernel 的文档字符串里有五十处 "returns nan"。整词匹配能挡住
#     returns，挡不住「how sharply the axis turns」。
#   * white —— Frank White 是流体力学教材的作者，而 `white` 是 CSS 关键字：
#     `white-space: pre-wrap` 里 `-` 是非单词字符，整词匹配照样命中。手册
#     站点的每一页都因此飘红过一次。
#
# 两者都留在这里，只会让闸门在**用不到它们的项目上**每次红一片，然后被人
# 关掉。真正用得到的那款 App（流体力学、燃烧）由【正典导出的名单】覆盖——
# 它们的作者就写在自己的 spec 里，导出得到的是精确的那一个。
#
# 这条取舍的一般形式：**防御名单只放不会误伤的姓氏；会误伤的靠正典导出。**
AUTHORS='anderson|cengel|hibbeler|incropera|moran|munson|roark|shigley|timoshenko'
if [ -r spec/specification.json ] && command -v python3 >/dev/null 2>&1; then
    DERIVED="$(python3 - spec/specification.json <<'PYEOF' 2>/dev/null || true
import json, re, sys
names = set()
for src in json.load(open(sys.argv[1], encoding="utf-8")).get("sources", []):
    if src.get("licence") != "copyrighted":
        continue                      # 公有领域来源【可以】具名，不该进这张表
    for token in re.split(r"[\s,]+", src.get("author", "")):
        token = token.strip(".")
        if len(token) > 2 and token.lower() != "and" and token.isalpha():
            names.add(token.lower())
print("|".join(sorted(names)))
PYEOF
)"
    [ -n "$DERIVED" ] && AUTHORS="$AUTHORS|$DERIVED"
fi
# 教材的编号体系。这些是「表达」，不是「事实」。
NUMBERING='Eq\.[[:space:]]*[0-9]|Example[[:space:]]+[0-9]|Problem[[:space:]]+[0-9]|Table[[:space:]]+[0-9]+-|Figure[[:space:]]+[0-9]+-|§[[:space:]]*[0-9]'

# ── 注释过滤：两个条件必须同时成立 ────────────────────────────────────────
#
# grep -rn 的输出形如  path:LINENO:内容 。注释标记出现在【内容】的开头，
# 不是行的开头。旧版写的是 '^\s*(//|#|\*)'，锚点落在 path 上——于是
# **一行注释都没排除掉**。它看起来一直是对的，因为「多抓」只会让闸门更严，
# 不会红得莫名其妙；只有拿一份【已知含注释违规】的样本去跑，才会发现
# 过滤器从来没有工作过。这正是阶段 S 那条纪律要防的东西。
#
# 第二个条件是扩展名。源码注释不进二进制，排除它合理；**资源文件会出货**，
# 而 Markdown 的 `# 标题` 与注释长得一模一样。只按标记过滤，会把
# 「# Hibbeler Table 3-2」这种真的会出现在用户眼前的字串静默放掉。
SOURCE_EXT='(swift|py|sh|mjs|js|ts|c|h|m)'
DROP_COMMENT="^[^:]*\.${SOURCE_EXT}:[0-9]+:[[:space:]]*(//|#|\*)"

# 姓氏必须匹配【整词】，编号体系不必。合起来跑一次 grep 的话，`turns`
# 会在每一句 "returns nan" 上命中——kernel 的文档字符串里有五十处。一个
# 每次都红五十行的闸门，两天之内就会被人关掉，这比没有闸门更糟。
scan_identifiers() {
    { grep -rnwEiI "$AUTHORS"   "$@" 2>/dev/null
      grep -rnEiI  "$NUMBERING" "$@" 2>/dev/null
    } | sort -u -t: -k1,1 -k2,2n | grep -vE "$DROP_COMMENT" || true
}

scan_constants() {
    # 界面层里出现多位小数的字面量，通常是把物理常数写进了界面。
    # 所有显示决策应当来自共用的 ui 决策层。
    grep -rnEI '[^0-9a-zA-Z_.][0-9]+\.[0-9]{3,}' "$@" --include="*.swift" 2>/dev/null \
        | grep -vE "$DROP_COMMENT|version|Version|[0-9]\.[0-9]+\.[0-9]" || true
}

# ── 自检 ─────────────────────────────────────────────────────────────────
# 跑的是【完整管线】，不是里面的 grep。上一版自检只喂 grep、绕过了过滤器，
# 所以过滤器坏了两年而自检一直报绿。样本必须同时覆盖两个方向：
# 真违规漏掉 = 闸门失效；合规误判 = 闸门会被人关掉。
selftest() {
    local T; T="$(mktemp -d)" || return 1
    printf 'let note = "see Gere Eq. 5-12"\n'                 > "$T/code_violation.swift"
    printf '    // Timoshenko §2.4, Eq. 2-11 —— 内部出处，不出货\n' > "$T/comment_only.swift"
    printf '# Hibbeler Table 3-2\n'                           > "$T/resource.md"
    printf 'let ok = "verified against NASA reference data"\n' > "$T/clean.swift"
    printf 'let doc = "the function returns nan out of domain"\n' > "$T/substring.swift"
    printf '.formula { white-space: pre-wrap; word-break: break-word; }\n' > "$T/style.css"
    printf 'let poissonRatio = 0.3333333\n'                   > "$T/const_violation.swift"
    printf 'let appVersion = 1.2345\n    // scale factor 0.123456\n' > "$T/const_clean.swift"

    local ident const rc=0
    ident="$(scan_identifiers "$T")"
    const="$(scan_constants "$T")"
    rm -rf "$T"

    grep -q 'code_violation'  <<<"$ident" || { echo "${RED}自检失败：源码里的真违规没被抓到${OFF}" >&2; rc=1; }
    grep -q 'resource\.md'    <<<"$ident" || { echo "${RED}自检失败：资源文件的违规没被抓到——注释过滤越界到了会出货的文件${OFF}" >&2; rc=1; }
    grep -q 'comment_only'    <<<"$ident" && { echo "${RED}自检失败：源码注释没被排除——过滤器的锚点又落在 path 上了${OFF}" >&2; rc=1; }
    grep -q 'clean\.swift'    <<<"$ident" && { echo "${RED}自检失败：合规文本被误判${OFF}" >&2; rc=1; }
    grep -q 'substring'       <<<"$ident" && { echo "${RED}自检失败：'turns' 在 'returns' 里命中——姓氏必须匹配整词${OFF}" >&2; rc=1; }
    grep -q 'style\.css'      <<<"$ident" && { echo "${RED}自检失败：CSS 的 white-space 被当成姓氏——会误伤的姓氏不该进防御名单${OFF}" >&2; rc=1; }
    # 这一项自检问的是【导出有没有发生】，不是【导出了谁】。
    #
    # 上一版写死了两个姓氏，那是模板作者手上那个项目的教材作者。换一个项目、
    # 换一套参考书，自检立刻失败——而它报告的是「闸门自身不可信」，于是整道
    # 闸门被拒绝执行。一道会因为换了项目就拒绝工作的闸门，和一道被关掉的
    # 闸门没有区别。
    #
    # 改成：防御名单之外必须至少多出一个姓氏。这证明确实读了正典，且不需要
    # 知道正典里是谁。
    if [ -r spec/specification.json ]; then
        [ -n "$DERIVED" ] || {
            echo "${RED}自检失败：正典存在但没导出任何作者——名单退回了防御表${OFF}" >&2; rc=1; }
    fi
    grep -q 'const_violation' <<<"$const" || { echo "${RED}自检失败：界面常数没被抓到${OFF}" >&2; rc=1; }
    grep -q 'const_clean'     <<<"$const" && { echo "${RED}自检失败：版本号或注释被当成物理常数${OFF}" >&2; rc=1; }
    return $rc
}
selftest || { echo "${RED}${BOLD}闸门自身不可信，拒绝报告结果。${OFF}" >&2; exit 2; }

echo
echo "${BOLD}Gate 06 · 法律隔离${OFF}"

echo "${BOLD}教材标识${OFF}"
HITS="$(scan_identifiers "$@")"
if [ -n "$HITS" ]; then
    echo "  ${RED}✗${OFF} 界面层／资源里出现教材标识："
    echo "$HITS" | sed 's/^/      /'
    echo "      → 公式本身可以显示；书名、作者、式号不可以。"
    echo "      → 公有领域来源（NACA / NASA / NIST / IAPWS / CODATA）可以具名，"
    echo "        而且反而增强可信度。"
    FAIL=$((FAIL+1))
else
    echo "  ${GREEN}✓${OFF} 无教材标识（源码注释按内部出处豁免，资源文件不豁免）"
fi

if [ "$IDENTIFIERS_ONLY" -eq 1 ]; then
    echo
    [ "$FAIL" -eq 0 ] && { echo "${GREEN}${BOLD}Gate 06 教材标识通过（本次未查界面常数）。${OFF}"; echo; exit 0; }
    echo "${RED}${BOLD}未通过：$FAIL 项。${OFF}"; echo; exit 1
fi

echo
echo "${BOLD}界面不持有物理${OFF}"
CONST="$(scan_constants "$@")"
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

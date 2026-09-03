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

# 扫描目标不存在时【必须响】，不能报绿。
#
# grep 扫一个不存在的路径 = 零命中 = 「✓ 无教材标识」。闸门于是每次都通过，
# 而它一个字节也没读过。这不是假设：run_all_local.sh 里写的是模板项目的路径
# （swift/Sources/MechanicsOneApp），在任何一款【别的】App 上那个目录都不
# 存在，这一步于是常绿至今。
#
# run_gates.sh 的抬头就写着「一道报告『零命中 ✓』而其实没有运行的闸门，比
# 没有闸门更糟」。这里把那句话变成可执行的：路径错了就拒绝报告结果。
MISSING=""
for _t in "$@"; do [ -e "$_t" ] || MISSING="$MISSING $_t"; done
if [ -n "$MISSING" ]; then
    echo "${RED}${BOLD}闸门拒绝报告结果：以下扫描目标不存在${OFF}" >&2
    for _t in $MISSING; do echo "      $_t" >&2; done
    echo "      → 扫不存在的路径 = 零命中 = 假绿。请修正调用方写的路径。" >&2
    exit 2
fi

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

# 书名 = 【只从正典导出】，没有防御名单。
#
# 只查作者姓氏会漏掉一整类泄漏：**书名本身**。AboutView 里那句
# 「Structural mechanics, worked on the iPad.」在这道闸门下绿了很久——它一个
# 作者名都没提，可 `Structural Mechanics` 正是某本受版权教材的书名整串。
# check_manual_isolation.py 早就在导出书名，但它只扫 site/ 与两册手册；
# **<Core>App 的源码没有任何一道闸门在看书名**，而 SwiftUI 的 Text() 字面量
# 会原样进二进制。
#
# 三条限制与 check_manual_isolation.py 完全一致，缺一条闸门就会乱叫：
#
#   * **≥12 字符**。更短的书名多半只是普通词组。
#   * **公有领域来源不算**。它们可以具名，而且应该具名。
#   * **同一书名挂在两个以上作者名下 = 学科名，不是书名**。一个书名要能识别
#     一本书，它得对应唯一一个作者；对应两个以上，它携带的识别信息就是零。
#     实测：某项目三本书的 title 都是 `Mechanics of Materials`——那是课程名，
#     首页那句「mechanics of materials, worked interactively」一本书也没指。
#
# 第三条挡不住的，正是这次出事的那一种：**单作者的书名恰好就是学科名**
# （Durka 的 `Structural Mechanics`）。闸门会照报——它无从分辨，也不该猜。
# 处置是【改词】，不是关闸门：把界面上那句改成 structural analysis，成本是
# 一行；漏一次 5.6 是账号层判定。
derive_titles() {                     # $1 = 正典路径；输出 ERE 备选串
    python3 - "$1" <<'PYEOF' 2>/dev/null || true
import json, re, sys
try:
    sources = json.load(open(sys.argv[1], encoding="utf-8")).get("sources", [])
except Exception:
    sys.exit(0)
by_title = {}
for s in sources:                     # 歧义判定要看【全部】来源，不只受版权的
    t = (s.get("title") or "").strip().lower()
    if t:
        by_title.setdefault(t, set()).add((s.get("author") or "").strip().lower())
ambiguous = {t for t, a in by_title.items() if len(a) > 1}
out = set()
for s in sources:
    if s.get("licence") != "copyrighted":
        continue
    t = (s.get("title") or "").strip()
    if len(t) >= 12 and t.lower() not in ambiguous:
        out.add(re.sub(r"([.^$*+?()\[\]{}|\\])", r"\\\1", t))   # ERE 转义
print("|".join(sorted(out)))
PYEOF
}
TITLES=""
if [ -r spec/specification.json ] && command -v python3 >/dev/null 2>&1; then
    TITLES="$(derive_titles spec/specification.json)"
fi
IDENT_WORDS="$AUTHORS"
[ -n "$TITLES" ] && IDENT_WORDS="$IDENT_WORDS|$TITLES"

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

# 姓氏与书名必须匹配【整词】，编号体系不必。合起来跑一次 grep 的话，`turns`
# 会在每一句 "returns nan" 上命中——kernel 的文档字符串里有五十处。一个
# 每次都红五十行的闸门，两天之内就会被人关掉，这比没有闸门更糟。
scan_identifiers() {
    { grep -rnwEiI "$IDENT_WORDS" "$@" 2>/dev/null
      grep -rnEiI  "$NUMBERING"   "$@" 2>/dev/null
    } | sort -u -t: -k1,1 -k2,2n | grep -vE "$DROP_COMMENT" || true
}

# 自检要能拿【任意一份名单】跑完整管线，而不是只喂里面的 grep——那正是
# 上一版过滤器坏了两年没被发现的原因。bash 的 local 是动态作用域，所以
# 这里的赋值对 scan_identifiers 可见。
scan_with_words() {                   # $1 = 名单；其余 = 目录
    local IDENT_WORDS="$1"; shift
    scan_identifiers "$@"
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

    # 书名样本用一份【合成正典】导出，不用本项目的正典。理由与下面那条
    # 「导出有没有发生」完全相同：写死本项目的书名，换一个项目自检立刻失败，
    # 而它报告的是「闸门自身不可信」——于是整道闸门被拒绝执行。
    #
    # 合成正典同时覆盖四条判据，其中【三条是防止乱叫的】。一道只测「抓得到」
    # 的自检会诱使人把名单越放越宽，直到闸门每次红一片然后被关掉。
    cat > "$T/spec.json" <<'JSONEOF'
{"sources": [
  {"key": "cw-long",   "licence": "copyrighted",   "author": "Q. Exampleson",   "title": "Zylonic Beam Theory"},
  {"key": "cw-short",  "licence": "copyrighted",   "author": "R. Otherperson",  "title": "Short Bk"},
  {"key": "cw-share1", "licence": "copyrighted",   "author": "S. Thirdperson",  "title": "Shared Discipline Name"},
  {"key": "cw-share2", "licence": "copyrighted",   "author": "T. Fourthperson", "title": "Shared Discipline Name"},
  {"key": "pd-open",   "licence": "public-domain", "author": "U. Fifthperson",  "title": "Public Domain Handbook"}
]}
JSONEOF
    printf 'let s = "Zylonic Beam Theory, worked interactively"\n'    > "$T/title_violation.swift"
    printf 'let s = "shared discipline name, worked interactively"\n' > "$T/title_ok.swift"

    local ident const titles tident rc=0
    ident="$(scan_identifiers "$T")"
    const="$(scan_constants "$T")"
    titles="$(derive_titles "$T/spec.json")"
    # 名单为空时 grep 的空模式匹配一切，会让下面那条「抓得到」的断言假绿。
    tident="$(scan_with_words "${titles:-__no_titles_derived__}" "$T")"
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
    # ── 书名：一条「抓得到」，三条「不乱叫」，外加一条完整管线 ──────────
    grep -q 'Zylonic Beam Theory'    <<<"$titles" || { echo "${RED}自检失败：书名没有从正典导出——<Core>App 里的书名泄漏会全部漏过${OFF}" >&2; rc=1; }
    grep -q 'Short Bk'               <<<"$titles" && { echo "${RED}自检失败：12 字符以下的书名进了名单——普通词组会被当成书名${OFF}" >&2; rc=1; }
    grep -q 'Shared Discipline Name' <<<"$titles" && { echo "${RED}自检失败：同一书名挂在两个作者名下 = 学科名，不该进名单${OFF}" >&2; rc=1; }
    grep -q 'Public Domain Handbook' <<<"$titles" && { echo "${RED}自检失败：公有领域来源进了名单——它们可以具名，而且应该具名${OFF}" >&2; rc=1; }
    grep -q 'title_violation'        <<<"$tident" || { echo "${RED}自检失败：书名在【完整管线】里没被抓到——导出对了，管线没接上${OFF}" >&2; rc=1; }
    grep -q 'title_ok'               <<<"$tident" && { echo "${RED}自检失败：学科名被误判成书名${OFF}" >&2; rc=1; }
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

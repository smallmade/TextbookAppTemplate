#!/bin/bash
# Gate S —— 出货二进制卫生检查。
#
#   bash check_binary_hygiene.sh <路径> [额外禁用词...]
#
# <路径> 可以是 .app 目录、.pkg、.ipa，也可以是源码目录。
# 传 .pkg / .ipa 时会先展开到临时目录再查——**这是推荐用法**：
# 源码干净不等于二进制干净，资源文件、正典副本、第三方库都可能带进禁用字串。
#
# 退出码 0 = 通过，非 0 = 有命中，可直接接进 CI。
#
# 这个脚本守的是规范 v3.0 的架构不变量 4：
#
#     交付给 Apple 的二进制，其行为不得依赖包外的任何输入。
#
# 它存在的理由是两次真实事故：PlotOne 的 QAHooks（为自动截图留的环境变量
# 开关）与 Passthrough 的 VIDEOCONVERT_FFMPEG_DIR（能把执行的 ffmpeg 换成
# 任意路径）。两者都导致 Guideline 5.6 拒审——那是账号层判定，不是单个
# App 的问题。
#
# 注意它查的是**可解读性**，不是意图。一个机制即使无害、即使你解释得清，
# 只要它在二进制里读起来像一个隐藏开关，它就是 5.6 的材料。

set -uo pipefail

TARGET="${1:-}"
shift || true
EXTRA_WORDS=("$@")

if [ -z "$TARGET" ] || [ ! -e "$TARGET" ]; then
    echo "用法: bash check_binary_hygiene.sh <.app|.pkg|.ipa|源码目录> [额外禁用词...]" >&2
    exit 2
fi

RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; BOLD=$'\033[1m'; OFF=$'\033[0m'
FAILURES=0
STAGE=""
cleanup() { [ -n "$STAGE" ] && rm -rf "$STAGE"; }
trap cleanup EXIT

fail() { echo "  ${RED}✗${OFF} $1"; FAILURES=$((FAILURES + 1)); }
pass() { echo "  ${GREEN}✓${OFF} $1"; }
note() { echo "  ${YELLOW}−${OFF} $1"; }

# 哪几项真的跑了。
#
# 规范说的是「六项检查**全数**通过」，而这个脚本跑一次只查得到其中一半：
# 对源码目录跑 S-1..3，对成品包跑 S-4..6。两次都跑过才算数，而在这之前
# 结尾那句「Gate S 通过」是**对一半的检查说的**，读起来像对六项说的。
#
# 一道说「通过」而没说「通过了什么」的闸门，会被读成它没做过的保证。
RAN=()
SKIPPED=()
ran()     { RAN+=("$1"); }
skipped() { SKIPPED+=("$1"); }

# —— 展开 .pkg / .ipa ——
case "$TARGET" in
    *.pkg)
        STAGE="$(mktemp -d)"
        pkgutil --expand-full "$TARGET" "$STAGE/x" >/dev/null 2>&1 \
            || { echo "无法展开 pkg: $TARGET" >&2; exit 2; }
        TARGET="$(find "$STAGE/x" -maxdepth 6 -name "*.app" -type d | head -1)"
        [ -n "$TARGET" ] || { echo "pkg 里找不到 .app" >&2; exit 2; }
        ;;
    *.ipa)
        STAGE="$(mktemp -d)"
        unzip -q -o "$TARGET" -d "$STAGE/x" \
            || { echo "无法解压 ipa: $TARGET" >&2; exit 2; }
        TARGET="$(find "$STAGE/x/Payload" -maxdepth 1 -name "*.app" -type d | head -1)"
        [ -n "$TARGET" ] || { echo "ipa 里找不到 .app" >&2; exit 2; }
        ;;
esac

echo
echo "${BOLD}Gate S · 出货二进制卫生${OFF}"
echo "目标: $TARGET"
echo

IS_BUNDLE=false
[[ "$TARGET" == *.app ]] && IS_BUNDLE=true

# ══════════════════════════════════════════════════════════════
# S-1 / S-2 / S-3：源码层。只在传源码目录时跑。
# ══════════════════════════════════════════════════════════════
# 源码层的三张模式表。
#
# 每一条都必须在【标识符边界】上匹配，不能匹配到更长名字的内部。
# 这条纪律是被同一类缺陷咬过三次才写下来的：
#
#   * `turns` 命中了 kernel 里五十处 "returns nan"；
#   * 注释过滤的锚点落在 grep 输出的 path 上，一行注释都没排除掉；
#   * 而这里，`system(` 命中了 SwiftUI 的 `Font.system(.body)`——
#     **每一个 SwiftUI 应用都会满屏飘红**。
#
# 一个会乱叫的闸门两天之内就会被人关掉，那比没有闸门更糟。所以 `system(`
# 前面必须不是点号也不是标识符字符：C 的 `system("rm -rf")` 会被抓到，
# `Font.system(...)`、`Color.systemBackground` 不会。
S1_PATTERN='ProcessInfo\.processInfo\.environment|(^|[^.[:alnum:]_])getenv[[:space:]]*\('
S2_PATTERN='(^|[^.[:alnum:]_])Process[[:space:]]*\(\)|(^|[^.[:alnum:]_])posix_spawn[[:space:]]*\(|(^|[^.[:alnum:]_])system[[:space:]]*\(|/usr/bin/|/usr/sbin/|/opt/homebrew|/usr/local/bin|/opt/local'
S3_PATTERN='(^|[^.[:alnum:]_])dlopen[[:space:]]*\(|(^|[^.[:alnum:]_])dlsym[[:space:]]*\(|NSClassFromString|performSelector'

# 源码层自检：两个方向都要证。
#
# 「真违规漏掉」让闸门失效；「合规代码误判」让闸门被关掉。第二种更常见，
# 也更难发现——它不会报错，只会让人不再看它的输出。
source_selftest() {
    local T; T="$(mktemp -d)" || return 1
    printf 'let mode = ProcessInfo.processInfo.environment["QA"]\n' > "$T/bad1.swift"
    printf 'let out = Process()\n' > "$T/bad2.swift"
    printf 'let h = dlopen("/usr/lib/x.dylib", 0)\n' > "$T/bad3.swift"
    printf 'let f = Font.system(.body, design: .monospaced)\n' > "$T/ok1.swift"
    printf 'let c = Color.systemBackground\n' > "$T/ok2.swift"
    printf 'let n = beam.processed()\n' > "$T/ok3.swift"
    local rc=0
    grep -rnE "$S1_PATTERN" "$T/bad1.swift" >/dev/null 2>&1 || { echo "自检失败：S-1 漏了真违规" >&2; rc=1; }
    grep -rnE "$S2_PATTERN" "$T/bad2.swift" >/dev/null 2>&1 || { echo "自检失败：S-2 漏了真违规" >&2; rc=1; }
    grep -rnE "$S3_PATTERN" "$T/bad3.swift" >/dev/null 2>&1 || { echo "自检失败：S-3 漏了真违规" >&2; rc=1; }
    for good in ok1 ok2 ok3; do
        if grep -rnE "$S1_PATTERN|$S2_PATTERN|$S3_PATTERN" "$T/$good.swift" >/dev/null 2>&1; then
            echo "自检失败：合规代码被误判（$good）——闸门会因此被关掉" >&2; rc=1
        fi
    done
    rm -rf "$T"
    return $rc
}

if ! $IS_BUNDLE; then
    source_selftest || { echo "${RED}${BOLD}闸门自身不可信，拒绝报告结果。${OFF}" >&2; exit 2; }

    ran "S-1"
    echo "${BOLD}S-1 环境变量读取${OFF}"
    HITS="$(grep -rnE "$S1_PATTERN" "$TARGET" \
            --include="*.swift" --include="*.c" --include="*.m" 2>/dev/null || true)"
    if [ -n "$HITS" ]; then
        fail "出货代码读取环境变量："; echo "$HITS" | sed 's/^/      /'
        echo "      → 出货二进制不得由环境变量改变行为。测试/截图需求请移出出货路径。"
    else
        pass "无环境变量读取"
    fi

    echo
    ran "S-2"
    echo "${BOLD}S-2 进程派生与包外路径${OFF}"
    HITS="$(grep -rnE "$S2_PATTERN" "$TARGET" \
            --include="*.swift" --include="*.c" --include="*.m" 2>/dev/null || true)"
    if [ -n "$HITS" ]; then
        fail "派生进程或引用包外路径："; echo "$HITS" | sed 's/^/      /'
        echo "      → App 只能执行随自己签名、一起送审的 helper。"
    else
        pass "无进程派生／包外路径"
    fi

    echo
    ran "S-3"
    echo "${BOLD}S-3 动态代码加载${OFF}"
    HITS="$(grep -rnE "$S3_PATTERN" "$TARGET" \
            --include="*.swift" --include="*.m" 2>/dev/null || true)"
    if [ -n "$HITS" ]; then
        fail "动态代码加载："; echo "$HITS" | sed 's/^/      /'
    else
        pass "无动态代码加载"
    fi

    skipped "S-4"; skipped "S-5"; skipped "S-6"
    echo
    if [ "$FAILURES" -eq 0 ]; then
        echo "${GREEN}${BOLD}S-1 S-2 S-3 通过。${OFF}"
        echo "${YELLOW}S-4 S-5 S-6 未查${OFF} —— 它们只能对成品包跑，而【源码干净不等于"
        echo "二进制干净】：资源文件、正典副本、第三方库都可能带进禁用字串。"
    else
        echo "${RED}${BOLD}源码层 $FAILURES 项未通过。${OFF}"
    fi
    echo
    exit $((FAILURES > 0))
fi

# ══════════════════════════════════════════════════════════════
# S-4：成品字符串。不可省略——源码干净不等于二进制干净。
# ══════════════════════════════════════════════════════════════
BANNED=(
    # 已致 5.6 的两个实例，永久留在表里作为回归防护
    "QAHooks" "P4M_QA" "P4M_" "VIDEOCONVERT_FFMPEG_DIR"
    # 包外可执行文件的常见位置
    "/opt/homebrew" "/usr/local/bin" "/opt/local/bin" "/usr/sbin/" "/usr/bin/"
    # 隐藏开关的常见命名
    "QA_MODE" "DEBUG_MENU" "INTERNAL_ONLY" "STAGING_URL" "TEST_HOOK"
    # 构建机的家目录。
    #
    # 一个出货二进制里不该出现 /Users/ —— 它只可能来自把开发机的绝对路径
    # 烙进了产物，而那正是不变量 4 说的「行为依赖包外的输入」。
    #
    # 这一条是被 SwiftPM 咬出来的：给一个 executable target 声明 resources，
    # 它会生成一个 `Bundle.module` accessor，兜底路径是【本机构建目录的
    # 绝对路径】。而在开发期，那条兜底路径就是真正生效的那条——装配出来的
    # .app 从来没有自足过，换一台机器就会在启动时 trap。
    #
    # 二进制里那一行字串是唯一的痕迹。S-4 现在会看见它。
    "/Users/"
)
# macOS 自带 bash 3.2：set -u 下展开空数组会报 unbound，必须带默认值
BANNED+=(${EXTRA_WORDS[@]+"${EXTRA_WORDS[@]}"})
PATTERN="$(IFS='|'; echo "${BANNED[*]}")"

# 构建期出处 vs 运行期路径。
#
# 编译器和构建系统会把自己的命令行烙进产物：FFmpeg 把整条 configure 行存进
# 库里（`ffmpeg -version` 就是这么显示配置的），里面有 --cc=/usr/bin/clang、
# -isysroot /Applications/Xcode.app/... 等等。这些是**出处记录**，不是这个
# App 运行时会去碰的路径，和 5.6 毫无关系。
#
# 不过滤掉它们，这道闸门在任何带原生依赖的项目上都会满屏飘红——而一个会
# 乱叫的闸门，两天之内就会被人关掉。宁可让 /usr/bin 这类宽泛模式漏一点，
# 也不能让它每次都误报：真正致命的那几个词（QAHooks、自定义环境变量名）
# 是精确匹配，不受这条过滤影响。
PROVENANCE='--prefix=|--enable-|--disable-|-isysroot|--sysroot|configuration:|Apple clang version|InstalledDir'
# 调试映射（debug map）。
#
# 未 strip 的 Mach-O 里，每一个参与链接的目标文件都留着一条 N_OSO 记录，
# 内容是它在构建机上的绝对路径：`/Users/…/X.build/Axial.swift.o`。
# 那是**出处**，不是运行期路径——App 从不打开它们，而 Xcode 归档时会把
# 整张表 strip 掉。
#
# 但它和真正危险的那种绝对路径混在同一条模式下。区别在结尾：调试映射指向
# `.o` / `.swiftmodule` / `.dylib` 这类构建产物；而 `Bundle.module` 的兜底
# 路径指向 `.bundle`——一个代码会真的去【打开】的东西。
#
# 所以这里只放行以构建产物结尾的那些，其余的一律留着报出来。
# 顺带：出货打包会 strip，所以在真正送审的产物上这条过滤不该有任何作用。
PROVENANCE="$PROVENANCE"'|/Users/.*\.(o|swiftmodule|swiftdoc|swiftsourceinfo|dylib|a)$'

# 自检：先用一个必然命中的样本走一遍完整管线。
#
# 这一条是被自己咬过才加的：PROVENANCE 以 -- 开头，grep 把它当成了选项、
# 报错退出，而管线末端的 `|| true` 把错误吞掉，脚本于是报告「零命中 ✓」——
# 一道**静默放行**的闸门。它比没有闸门更糟：没有闸门时你还知道自己没检查。
SELFTEST="$(printf 'QAHooks\n--prefix=/usr/bin/clang\n' \
            | grep -iE "$PATTERN" | grep -vE -e "$PROVENANCE" || true)"
if [ "$SELFTEST" != "QAHooks" ]; then
    echo "  ${RED}✗${OFF} 自检失败：检查管线没有按预期工作，结果不可信" >&2
    echo "      期望只留下 QAHooks，实际得到：${SELFTEST:-（空）}" >&2
    exit 2
fi

ran "S-4"
echo "${BOLD}S-4 成品字符串${OFF}"
# NUL 分隔，不用词分割。
#
# 这一段原本是 `for f in $(find ...)`，而这个仓库的路径里有空格
# （"My Drive"、"APP-Development"）。用相对路径调用时它碰巧是对的；
# run_all.sh 传的是绝对路径，于是每一个文件名都被空格切成碎片，
# `[ -f "$f" ]` 全部为假，**循环一个文件都没检查，然后打印「零命中 ✓」**。
#
# 这正是本文件开头那句话的第二个实例：一道静默放行的闸门比没有闸门更糟。
# 所以下面除了修掉词分割，还数了一下到底看过几个 Mach-O——看过零个就是
# 未通过，不是通过。
S4_HIT=false
S4_SEEN=0
while IFS= read -r -d '' f; do
    file "$f" | grep -q "Mach-O" || continue
    S4_SEEN=$((S4_SEEN+1))
    HITS="$(strings -a - "$f" 2>/dev/null | grep -iE "$PATTERN" \
            | grep -vE -e "$PROVENANCE" | sort -u || true)"
    if [ -n "$HITS" ]; then
        fail "${f#$TARGET/}"; echo "$HITS" | sed 's/^/        /'
        S4_HIT=true
    fi
done < <(find "$TARGET" -type f \
              \( \( -perm +111 ! -name "*.plist" \) -o -name "*.dylib" \) \
              -print0 2>/dev/null)
if [ "$S4_SEEN" -eq 0 ]; then
    fail "一个 Mach-O 都没看到——这不是零命中，这是没检查"
    S4_HIT=true
fi
$S4_HIT || pass "$S4_SEEN 个 Mach-O 文件零命中"

# ══════════════════════════════════════════════════════════════
# S-5：外部链接。不得链接到包外的任何东西。
# ══════════════════════════════════════════════════════════════
echo
ran "S-5"
echo "${BOLD}S-5 外部链接${OFF}"
MAIN="$TARGET/Contents/MacOS/$(basename "$TARGET" .app)"
[ -f "$MAIN" ] || MAIN="$TARGET/$(basename "$TARGET" .app)"
if [ -f "$MAIN" ]; then
    HITS="$(otool -L "$MAIN" 2>/dev/null | tail -n +2 \
            | grep -vE "@rpath|@executable_path|@loader_path|/usr/lib/|/System/" || true)"
    if [ -n "$HITS" ]; then
        fail "链接到包外："; echo "$HITS" | sed 's/^/      /'
    else
        pass "只链接 @rpath / 系统库"
    fi
else
    note "找不到主可执行文件，跳过"
fi

# ══════════════════════════════════════════════════════════════
# S-6：签名 entitlements。守 90886 与 get-task-allow。
# ══════════════════════════════════════════════════════════════
echo
echo "${BOLD}S-6 签名 entitlements${OFF}"
ENT="$(codesign -d --entitlements - --xml "$TARGET" 2>/dev/null | plutil -p - 2>/dev/null || true)"
if [ -z "$ENT" ]; then
    skipped "S-6"
    note "未签名或读不到 entitlements，跳过"
else
    ran "S-6"
    if echo "$ENT" | grep -q 'get-task-allow" => true'; then
        fail "get-task-allow 为 true —— 这是调试签名，不能上架"
    else
        pass "get-task-allow 不为 true"
    fi

    HAS_PROFILE=false
    [ -f "$TARGET/Contents/embedded.provisionprofile" ] && HAS_PROFILE=true
    [ -f "$TARGET/embedded.mobileprovision" ] && HAS_PROFILE=true

    if $HAS_PROFILE; then
        # iOS 的键是 application-identifier，macOS 带 com.apple. 前缀，两个都要认
        if echo "$ENT" | grep -qE '"(com\.apple\.)?application-identifier"'; then
            BID="$(plutil -extract CFBundleIdentifier raw "$TARGET/Contents/Info.plist" 2>/dev/null \
                   || plutil -extract CFBundleIdentifier raw "$TARGET/Info.plist" 2>/dev/null || true)"
            if [ -n "$BID" ] && echo "$ENT" | grep -q "$BID"; then
                pass "identifier 已签进，且指向 $BID"
            else
                fail "identifier 已签进，但不指向本 bundle id（$BID）"
            fi
        else
            fail "内嵌了描述文件却没把 application-identifier 签进去 —— 这就是 90886"
            echo "      → 从描述文件的 Entitlements 并入 application-identifier"
            echo "        与 com.apple.developer.team-identifier 后重签。"
        fi
        echo "$ENT" | grep -q "team-identifier" \
            && pass "team-identifier 已签进" \
            || fail "缺 com.apple.developer.team-identifier"
    else
        note "包内无描述文件，跳过 identifier 检查"
    fi
fi

# ══════════════════════════════════════════════════════════════
skipped "S-1"; skipped "S-2"; skipped "S-3"
echo
if [ "$FAILURES" -eq 0 ]; then
    echo "${GREEN}${BOLD}$(IFS=' '; echo "${RAN[*]}") 通过。${OFF}"
    if [ ${#SKIPPED[@]} -gt 0 ]; then
        echo "${YELLOW}$(IFS=' '; echo "${SKIPPED[*]}") 未查${OFF} —— S-1..3 要对源码目录跑，"
        echo "S-6 要对已签名的包跑。规范说的是【六项全数通过】，两次都跑过才算。"
    fi
    echo
    exit 0
else
    echo "${RED}${BOLD}Gate S 未通过：$FAILURES 项。${OFF}"
    echo "在这些修掉之前不要投递 —— 它们的代价是账号，不是一次重新提交。"
    echo
    exit 1
fi

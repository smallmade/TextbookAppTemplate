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
if ! $IS_BUNDLE; then
    echo "${BOLD}S-1 环境变量读取${OFF}"
    HITS="$(grep -rn "ProcessInfo\.processInfo\.environment\|getenv(" "$TARGET" \
            --include="*.swift" --include="*.c" --include="*.m" 2>/dev/null || true)"
    if [ -n "$HITS" ]; then
        fail "出货代码读取环境变量："; echo "$HITS" | sed 's/^/      /'
        echo "      → 出货二进制不得由环境变量改变行为。测试/截图需求请移出出货路径。"
    else
        pass "无环境变量读取"
    fi

    echo
    echo "${BOLD}S-2 进程派生与包外路径${OFF}"
    HITS="$(grep -rn "Process()\|posix_spawn\|system(\|/usr/bin/\|/usr/sbin/\|/opt/homebrew\|/usr/local/bin\|/opt/local" \
            "$TARGET" --include="*.swift" --include="*.c" --include="*.m" 2>/dev/null || true)"
    if [ -n "$HITS" ]; then
        fail "派生进程或引用包外路径："; echo "$HITS" | sed 's/^/      /'
        echo "      → App 只能执行随自己签名、一起送审的 helper。"
    else
        pass "无进程派生／包外路径"
    fi

    echo
    echo "${BOLD}S-3 动态代码加载${OFF}"
    HITS="$(grep -rn "dlopen\|dlsym\|NSClassFromString\|performSelector" "$TARGET" \
            --include="*.swift" --include="*.m" 2>/dev/null || true)"
    if [ -n "$HITS" ]; then
        fail "动态代码加载："; echo "$HITS" | sed 's/^/      /'
    else
        pass "无动态代码加载"
    fi

    echo
    if [ "$FAILURES" -eq 0 ]; then
        echo "${GREEN}${BOLD}源码层通过。${OFF}提交前务必再对成品包跑一次本脚本。"
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

echo "${BOLD}S-4 成品字符串${OFF}"
EXECUTABLES="$(find "$TARGET" -type f -perm +111 ! -name "*.dylib" ! -name "*.plist" 2>/dev/null)"
DYLIBS="$(find "$TARGET" -type f -name "*.dylib" -o -type f -path "*.framework/*" -perm +111 2>/dev/null)"
S4_HIT=false
for f in $EXECUTABLES $DYLIBS; do
    [ -f "$f" ] || continue
    file "$f" | grep -q "Mach-O" || continue
    HITS="$(strings -a - "$f" 2>/dev/null | grep -iE "$PATTERN" \
            | grep -vE -e "$PROVENANCE" | sort -u || true)"
    if [ -n "$HITS" ]; then
        fail "${f#$TARGET/}"; echo "$HITS" | sed 's/^/        /'
        S4_HIT=true
    fi
done
$S4_HIT || pass "所有 Mach-O 文件零命中"

# ══════════════════════════════════════════════════════════════
# S-5：外部链接。不得链接到包外的任何东西。
# ══════════════════════════════════════════════════════════════
echo
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
    note "未签名或读不到 entitlements，跳过"
else
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
echo
if [ "$FAILURES" -eq 0 ]; then
    echo "${GREEN}${BOLD}Gate S 通过。${OFF}"
    echo
    exit 0
else
    echo "${RED}${BOLD}Gate S 未通过：$FAILURES 项。${OFF}"
    echo "在这些修掉之前不要投递 —— 它们的代价是账号，不是一次重新提交。"
    echo
    exit 1
fi

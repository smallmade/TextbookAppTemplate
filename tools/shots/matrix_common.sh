#!/usr/bin/env bash
# [M-C1] 设备矩阵采集的共用件：守卫、档位读取、产物登记。
#
# 三款 App 共用。**不要在这里写任何一款 App 的名字**——App 的形状全部从
# 项目根的 ci.toml 读（tools/ci/ci_config.py 的同一套约定）。这个文件曾经
# 是不存在的：Mac 那一半与 iPad 那一半各自抄了一遍守卫，于是锁屏守卫在
# 其中一半里少了一行、没人发现。
#
# 这里的每一个 matrix::guard_* 都对应一次真实事故，见各函数上的注释。
#
# 用法：`source tools/shots/matrix_common.sh`，然后调 matrix::*。

# ── 守卫 1 · 锁屏 ─────────────────────────────────────────────────────
#
# 锁屏时 System Events 对一个【真在跑】的进程报「0 windows」，CGWindowList
# 也一个都不返回。看起来和脚本 bug、和跨会话抢窗口一模一样，姊妹项目为此
# 误诊过两次。所以先查这一条，查不过就退出并说清楚，绝不往下走。
#
# 探针单独一个函数，是为了自检能替换它——一道「没找到问题就算通过」的
# 检查，必须有一个已知会失败的样本证明它真的在工作（规范 v4.0 阶段 S）。
matrix::_lock_probe() {
    ioreg -n Root -d1 -a 2>/dev/null | plutil -p - 2>/dev/null
}

matrix::guard_unlocked() {
    local locked
    locked="$(matrix::_lock_probe \
        | grep -c 'CGSSessionScreenIsLocked" => true' || true)"
    if [ "$locked" != "0" ]; then
        echo "✗ 屏幕锁着。" >&2
        echo "  锁屏时 System Events 与 CGWindowList 对一个真在跑的进程都报" >&2
        echo "  「0 windows」，任何按窗口 ID 的截图都拿不到东西。这不是脚本" >&2
        echo "  坏了，也不是别的会话在抢——解锁后重跑。" >&2
        echo "  自查：ioreg -n Root -d1 -a | plutil -p - | grep CGSSessionScreenIsLocked" >&2
        return 1
    fi
    return 0
}

# ── 守卫 2 · 不在 Google Drive 路径下跑签过名的 Release ────────────────
#
# 项目在 File Provider 挂载点上，loader 映回来的页与它验过的页不是同一批，
# 内核直接 SIGKILL（Console 里是 CODESIGNING / Invalid Page）。拷到本地盘
# 并去掉 File Provider 补的扩展属性，再 ad-hoc 重签。
matrix::stage_mac_app() {
    local src="$1" stage="$2"
    local name; name="$(basename "$src")"
    rm -rf "$stage"; mkdir -p "$stage"
    # -X 丢掉扩展属性：`.framework` 带着 FinderInfo 会让 codesign 拒绝，
    # 报 `resource fork detritus`。
    cp -RX "$src" "$stage/" || return 1
    xattr -cr "$stage/$name" 2>/dev/null || true
    codesign --force --deep --sign - "$stage/$name" >/dev/null 2>&1 || true
    echo "$stage/$name"
}

# ── bash 3.2 ──────────────────────────────────────────────────────────
#
# macOS 自带的是 bash 3.2（GPLv3 之后 Apple 就没再升过），**没有 mapfile**。
# 第一版用了 mapfile，于是 iPad 那一半在 `mapfile: command not found` 之后
# 带着一串 unbound variable 一路跑到底、打印「登记」、退 1——错误信息在
# 六百行输出的第 8 行，看起来像是矩阵没采到东西，而不是脚本根本没跑。
#
#   matrix::readlines <数组名> < <(命令)
matrix::readlines() {
    local __name="$1" __line
    eval "$__name=()"
    while IFS= read -r __line; do
        eval "$__name+=(\"\$__line\")"
    done
}

# ── 项目形状 ──────────────────────────────────────────────────────────
#
# 这一节以前是不存在的：App 的路径、进程名、落地目录、模拟器设备名全部
# **写死在脚本里**，于是这套工具在别的项目上只能靠再抄一份来用。抄一份的
# 代价本系列已经付过：`run_all_local.sh` 写死了 `--mine "Material Mechanics
# Calculator"`，热力学那一款跑起来时报的是别人那一格——不会红，只会答错。
#
# 形状读 ci.toml 的 `[shots]` 一节，读取器是 tools/shots/shots_config.py。
# `matrix::init` 会把它 eval 进来，于是脚本里能直接用 `$SHOTS_MAC_APP`。
matrix::load_config() {
    local shell_vars
    shell_vars="$(python3 "$MATRIX_ROOT/tools/shots/shots_config.py" \
        --root "$MATRIX_ROOT" --shell)" || {
        echo "✗ 读不到 $MATRIX_ROOT/ci.toml 的 [shots] 一节。" >&2
        echo "  取证工具不猜项目的形状——猜错时它不会红，只会拍错东西。" >&2
        echo "  看它要什么：python3 tools/shots/shots_config.py --describe" >&2
        return 1; }
    eval "$shell_vars"
}

# ── 档位 ──────────────────────────────────────────────────────────────
#
# 首选真身是 ci.toml 顶层的 [[devices]]，闸门（check_device_matrix.py）读的
# 是同一处。采集工具和闸门读两份清单，是「已填 612 格」和「闸门要 684 格」
# 同时成立的那种错法。
#
# 顶层没有时读 [[shots.devices]]，并且**把这件事印出来**——见 shots_config.py
# 里 devices() 的说明。
#
#   matrix::tiers <mac|ipad|all>
#   → name<TAB>platform<TAB>width<TAB>height<TAB>devicetype<TAB>orientation<TAB>split<TAB>manual
matrix::tiers() {
    python3 "$MATRIX_ROOT/tools/shots/shots_config.py" \
        --root "$MATRIX_ROOT" --tiers "${1:-all}"
}

# 画面清单。**形状由项目声明**（screens_kind），不猜：
#   screenspec     Swift 源里的 ScreenSpec(id:…, title:…)
#   canon-sections 分节表定顺序、正典定内容
# 拿前一种的正则去扫后一种，得到的是零个画面——而零个画面在这里必须是
# 未通过，不能是「没有画面要拍，收工」。
#
#   matrix::screens        → 一行一个画面 id
#   matrix::screen_titles  → 一行一个画面标题（顺序与上面一一对应）
matrix::screens() {
    python3 "$MATRIX_ROOT/tools/shots/shots_config.py" \
        --root "$MATRIX_ROOT" --screens
}

matrix::screen_titles() {
    python3 "$MATRIX_ROOT/tools/shots/shots_config.py" \
        --root "$MATRIX_ROOT" --screen-titles
}

# ── 产物登记 ──────────────────────────────────────────────────────────
#
# 每一格【无论成没成】都要登记一行。只登记成功的那些，等于把「这一档本机
# 屏幕放不下」和「这一档没跑」写成同一件事——而它们是两件事。
#
#   matrix::record <status> <device> <screen> <appearance> \
#                  <want_w> <want_h> <got_w> <got_h> <file> <note>
#
# status: ok | size-mismatch | unreachable | manual | switch-failed | launch-failed
matrix::record() {
    local px_w="" px_h="" status="$1" note="${10:-}"
    if [ -n "${9:-}" ] && [ -f "${9}" ]; then
        read -r px_w px_h <<<"$(matrix::pixels "$9")"
    fi
    # 这一格的图，是【这一轮】拍的吗。
    #
    # 上一轮留在目录里的 PNG 会让这一轮的失败看起来像成功：采集在锁屏下第一台
    # 设备就够不着辅助功能桥、一张都没拍，而登记表照样报「ok 8」——那 8 行是照
    # 目录里已有的文件生成的。这正是这整套工具链在治的那一类：一道「没找到问题
    # 就算通过」的检查，只是这次它换到了产物这一头。
    #
    # 判据用 mtime 而不是「文件存不存在」：存在只说明有人拍过，不说明是刚才。
    if [ "$status" = "ok" ] && [ -n "${9:-}" ]; then
        if [ ! -f "${9}" ]; then
            status="missing-file"
            note="登记为 ok 但文件不在：${9}｜$note"
        elif [ "${9}" -ot "$MATRIX_RUN_STAMP" ]; then
            status="stale-evidence"
            note="这张图是上一轮留下的，不是本轮拍的（早于本轮开始时刻）｜$note"
        fi
    fi
    set -- "$status" "$2" "$3" "$4" "$5" "$6" "$7" "$8" "${9:-}" "$note"
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$1" "$2" "$3" "$4" "$5" "$6" "$7" "$8" \
        "${px_w:-}" "${px_h:-}" "${9:-}" "${10:-}" >> "$MATRIX_MANIFEST"
}

# 两张图逐字节相同吗。iPad 那一半唯一抓得住「18 张同一屏」的地方，
# 所以它是个具名函数而不是一行内联——自检要指着它跑。
matrix::same_image() {   # <a> <b> → 相同则 0
    [ -f "$1" ] && [ -f "$2" ] || return 1
    [ "$(shasum -a 256 "$1" | cut -d' ' -f1)" \
      = "$(shasum -a 256 "$2" | cut -d' ' -f1)" ]
}

matrix::pixels() {
    sips -g pixelWidth -g pixelHeight "$1" 2>/dev/null \
        | awk '/pixelWidth/{w=$2} /pixelHeight/{h=$2} END{print w, h}'
}

# 文件名。check_device_matrix.py 的判据：三段都出现在文件名里，`__` 分隔。
matrix::filename() {   # <device> <screen> <appearance>
    printf '%s__%s__%s.png' "$1" "$2" "$3"
}

# ── 窗口身份 ──────────────────────────────────────────────────────────
#
# **CGWindow 的 owner name 不一定等于 System Events 的进程名。**
# 实测：StructureMechOne 的 `CFBundleDisplayName` 是「Truss Frame」，于是
# 辅助功能层叫它 StructureMechOne，而 CGWindowList 里它的 owner 是
# Truss Frame。按进程名去 CGWindowList 里找，一个窗口也找不到——而
# `WindowID.swift` 找不到时只是**退 1、什么都不印**，看起来像 App 没起来。
#
# 所以按 **pid** 找：pid 是同一个身份，两侧不会各说各话，也顺带证明拍到的
# 那个窗口确实属于我们驱动的那个进程（这台机器上常年有别的会话在开窗口）。
matrix::app_pid() {   # <System Events 里的进程名> → pid，找不到则退 1
    local pid
    pid="$(osascript -e "tell application \"System Events\" to get unix id of process \"$1\"" 2>/dev/null)"
    [ -n "$pid" ] || return 1
    echo "$pid"
}

matrix::window_id() {   # <进程名> → CGWindowID，拿不到则退 1
    local pid
    pid="$(matrix::app_pid "$1")" || return 1
    swift "$MATRIX_ROOT/tools/shots/WindowID.swift" --pid "$pid" 2>/dev/null
}

# ── 切屏 ──────────────────────────────────────────────────────────────
#
# 侧栏的行不一定和画面一一对应：**分节标题也占一行**。StructureMechOne 的
# 侧栏有 53 行 = 45 屏 + 8 个分节标题，而 MechanicsOne 是 18 行 = 18 屏。
# 把「第 i 屏 = 第 i 行」写死在脚本里，在前者身上会从第 4 屏起整体错位——
# 而每一张图都拍得出来、每一张都不是空的，**登记表会是满的**。
#
# 所以按标题找行，而不是按序号算行：从 `$MATRIX_ROW` 开始往下选，直到窗口
# 标题变成这一屏该有的那个。分节标题选不动（选它是空操作），于是它被自然
# 跳过；真的够不着时会一路扫到底再失败，而不是拍下一张不知道是哪屏的图。
#
# 判据是**标题对得上**，不是「标题变了」——后者分不出「切到了第 3 屏」和
# 「切到了第 7 屏」。这一条是 walkthrough_mac.sh 用 18 张同一屏的图换来的。
#
#   matrix::rows <进程名> <AX 行路径>   → 侧栏有几行（拿不到则 0）
#   matrix::select_screen <进程名> <AX 行路径> <期望标题> <总行数>
#     命中退 0，把实际标题放进 **MATRIX_TITLE**；否则退 1，最后看到的标题
#     放进 MATRIX_LAST_TITLE。
#
# 结果走全局变量而不是 stdout，是因为 `$( )` 会开一个子 shell，而 MATRIX_ROW
# 在子 shell 里前进了、回到父 shell 就丢了——那样每一屏都从第 1 行重扫，
# 45 屏要多花二十分钟，而且**看不出来**：图照拍、登记表照满。
#
# 副作用：MATRIX_ROW 前进到命中那一行的**下一行**。调用方在换设备/换外观
# 后要把它重置为 1。
matrix::rows() {
    local n
    n="$(osascript -e "tell application \"System Events\" to tell process \"$1\" \
        to get count of rows of $2" 2>/dev/null)"
    echo "${n:-0}"
}

matrix::select_screen() {
    local proc="$1" rowpath="$2" want="$3" limit="${4:-200}"
    local title=""
    MATRIX_ROW="${MATRIX_ROW:-1}"
    MATRIX_TITLE=""
    while [ "$MATRIX_ROW" -le "$limit" ]; do
        osascript -e "tell application \"System Events\" to tell process \"$proc\" \
            to select row $MATRIX_ROW of $rowpath" >/dev/null 2>&1
        sleep 0.7
        title="$(osascript -e "tell application \"System Events\" to tell process \"$proc\" \
            to get title of window 1" 2>/dev/null || echo "")"
        if [ -n "$title" ] && [[ "$title" == *"$want"* ]]; then
            MATRIX_TITLE="$title"
            MATRIX_ROW=$((MATRIX_ROW+1))
            return 0
        fi
        MATRIX_ROW=$((MATRIX_ROW+1))
    done
    MATRIX_LAST_TITLE="$title"
    return 1
}

matrix::init() {
    MATRIX_ROOT="${MATRIX_ROOT:?matrix::init 之前要设 MATRIX_ROOT}"
    matrix::load_config || return 1
    MATRIX_OUT="${MATRIX_OUT:?matrix::init 之前要设 MATRIX_OUT}"
    MATRIX_MANIFEST="$MATRIX_OUT/_manifest.tsv"
    mkdir -p "$MATRIX_OUT"
    # 本轮的开始时刻，用一个真实文件承载——`-ot` 比较的是文件不是字符串，
    # 而这样也就不必猜这台机器的 `stat` 是 BSD 还是 GNU 的那一种。
    MATRIX_RUN_STAMP="$MATRIX_OUT/.run-stamp"
    : > "$MATRIX_RUN_STAMP"
    sleep 1   # mtime 的分辨率是秒；同一秒内拍出来的图不该被判成上一轮的
    if [ ! -f "$MATRIX_MANIFEST" ]; then
        printf 'status\tdevice\tscreen\tappearance\twant_w\twant_h\tgot_w\tgot_h\tpx_w\tpx_h\tfile\tnote\n' \
            > "$MATRIX_MANIFEST"
    fi
}

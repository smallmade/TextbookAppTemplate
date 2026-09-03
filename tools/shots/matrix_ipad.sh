#!/usr/bin/env bash
# [M-C1] 设备矩阵 · iPad 那一半：机型 × 朝向 × 全部画面 × 深浅色。
#
#   bash tools/shots/matrix_ipad.sh <输出目录> [--devices a,b] [--screens N]
#                                   [--headless]
#
# ## 模拟器是共享资源
#
# 这台机器上常年有姊妹会话开着模拟器。`xcrun simctl ... booted` 会替你挑
# 一台【别人的】——姊妹项目的截图曾经中途变成了另一款 App 的画面，而没有
# 任何东西报错。所以：先列出已开着的（让人看见现场），再新建一台**专用
# 设备**，跑完删掉。绝不碰别人那台。
#
# ## 截图与切屏是两条不同的通道
#
#   截图  `xcrun simctl io <udid> screenshot` —— 直接抓设备帧缓冲，尺寸正好
#         是屏幕点数 × 倍率，没有窗口边框，锁屏也能抓。这是矩阵要的东西。
#   切屏  只能走 Simulator.app 的辅助功能桥（macOS 的 System Events 能看到
#         模拟器里 App 的元素）。`simctl` **没有**任何输入子命令——没有 tap、
#         没有按键、没有旋转。这不是本脚本偷懒，是 simctl 的能力边界：
#         `xcrun simctl help` 里 io / ui / openurl 都在，输入一个都没有。
#
# 所以 iPad 这一半需要**解锁的屏幕**（Simulator.app 要有真实窗口），尽管
# 截图本身不需要。`--headless` 只跑得到开屏那一屏，用于冒烟。
#
# ## 切屏的核对
#
# Mac 那一半有独立证据（窗口标题就是画面名）。iPad 没有等价的东西，所以
# 用两条合起来：点击是**按名字**打中的（`whose name is "Columns"`，打不中
# 直接失败，不是警告），并且**这一张图必须和上一张不同**。后者专抓那个
# 已经发生过的事故：18 次切换全部失败、存下 18 张同一屏的图、打印「完成」。
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=matrix_common.sh
source "$ROOT/tools/shots/matrix_common.sh"

MATRIX_ROOT="$ROOT"
MATRIX_OUT="${1:?用法: matrix_ipad.sh <输出目录> [--devices a,b] [--screens N] [--headless]}"
shift || true
ONLY_DEVICES=""; MAX_SCREENS=0; HEADLESS=0
while [ $# -gt 0 ]; do
    case "$1" in
        --devices)  ONLY_DEVICES="$2"; shift 2 ;;
        --screens)  MAX_SCREENS="$2"; shift 2 ;;
        --headless) HEADLESS=1; shift ;;
        *) echo "不认识的参数：$1" >&2; exit 2 ;;
    esac
done
matrix::init || exit 1

# 形状读 ci.toml 的 [shots]，不写死任何一款 App 的名字。见 shots_config.py。
APP_SRC="$ROOT/${SHOTS_IPAD_APP:?ci.toml 的 [shots] 没有 ipad_app}"
STAGE="/private/tmp/${SHOTS_STAGE_PREFIX:-shots}-device-matrix-ipad"
SIM_PREFIX="${SHOTS_STAGE_PREFIX:-shots}"
[ -d "$APP_SRC" ] || {
    echo "✗ 没有 $APP_SRC —— 先 ${SHOTS_IPAD_BUILD_HINT:-建出 iPad 模拟器包}。" >&2
    exit 2; }
BUNDLE_ID="$(plutil -extract CFBundleIdentifier raw "$APP_SRC/Info.plist" 2>/dev/null)"
[ -n "$BUNDLE_ID" ] || { echo "✗ 读不到 iPad 包的 bundle id" >&2; exit 1; }

RUNTIME="$(xcrun simctl list runtimes 2>/dev/null \
    | awk '/^iOS /{print $NF}' | tail -1)"
[ -n "$RUNTIME" ] || { echo "✗ 没有可用的 iOS runtime" >&2; exit 2; }

matrix::readlines SCREEN_IDS    < <(matrix::screens)
matrix::readlines SCREEN_TITLES < <(matrix::screen_titles)
N_SCREENS="${#SCREEN_IDS[@]}"
[ "$N_SCREENS" -gt 0 ] || { echo "✗ 一个画面都没解析到——零个不是通过。" >&2; exit 1; }
[ "$MAX_SCREENS" -gt 0 ] && [ "$MAX_SCREENS" -lt "$N_SCREENS" ] \
    && N_SCREENS="$MAX_SCREENS"

echo "── 现场：已经开着的模拟器（别人的，不碰）──"
xcrun simctl list devices booted 2>/dev/null | sed 's/^/   /'

CREATED=()
cleanup() {
    for udid in "${CREATED[@]:-}"; do
        [ -n "$udid" ] || continue
        xcrun simctl shutdown "$udid" >/dev/null 2>&1 || true
        xcrun simctl delete   "$udid" >/dev/null 2>&1 || true
    done
    rm -rf "$STAGE"
}
trap cleanup EXIT INT TERM

# 拷出 Drive 再装：File Provider 会给包补扩展属性，install 未必挂，但
# 一条纪律执行两处比记住「这一处不需要」可靠。
rm -rf "$STAGE"; mkdir -p "$STAGE"
cp -RX "$APP_SRC" "$STAGE/"
xattr -cr "$STAGE/$(basename "$APP_SRC")" 2>/dev/null || true
APP="$STAGE/$(basename "$APP_SRC")"

sim_ax() {   # 一段 AppleScript，跑在 Simulator 进程里
    osascript -e "tell application \"System Events\" to tell process \"Simulator\" to $1" 2>&1
}

# 把**我们这一台**的窗口顶到最前，并确认它就是 window 1。
#
# 为什么不能省这一步：这台 Mac 上同时跑着多个 Claude 会话，Simulator.app 是
# 所有会话共用的**一个进程**，每台开机的设备各占一个窗口。实测过一次现场：
# 五个窗口全是别的会话的设备，而本脚本原先按 `window 1` 定位。
#
# 后果不是「找不到元素就失败」这么轻——`sim_rotate_to` 用的是 Device 菜单，
# 而菜单作用在**最前面那个窗口**上。也就是说，原先这段代码在别人开着模拟器时
# 会去**旋转别人的设备**，而本脚本这边只会看到一张方向不对的截图。
#
# 所以每一次 AX 交互之前都先按**设备名**把自己的窗口顶上来。名字是
# `<stage_prefix>-matrix-<pid>-...`，进程号使它在并发会话之间也是唯一的。
sim_focus_window() {   # <设备名>
    osascript <<APPLESCRIPT 2>&1
tell application "System Events" to tell process "Simulator"
    set mine to (every window whose name starts with "$1")
    if mine is {} then error "no-window"
    set w to item 1 of mine
    -- Simulator 记住上一次的窗口位置，而六个窗口一路层叠下去之后，新开的那个
    -- 会落在屏幕之外（实测拿到过 {-402, -934}）。屏幕外的窗口点不到也拍不好，
    -- 而它报的错和「元素名变了」长得一模一样。先搬回来。
    set {px, py} to position of w
    if px < 0 or py < 0 then set position of w to {60, 40}
    perform action "AXRaise" of w
    set frontmost to true
end tell
APPLESCRIPT
    sleep 0.6
}

# 按名字点一行。打不中就失败——不是警告。
#
# 窗口按**设备名**取，不是 `window 1`：见 sim_focus_window 的说明。
sim_click_named() {   # <设备名> <元素名>
    osascript <<APPLESCRIPT 2>&1
tell application "System Events" to tell process "Simulator"
    set mine to (every window whose name starts with "$1")
    if mine is {} then error "no-window"
    set w to item 1 of mine
    set hits to (every item of (entire contents of w) whose name is "$2")
    if hits is {} then error "no-element"
    click item 1 of hits
end tell
APPLESCRIPT
}

# 旋转靠菜单项（元素定位，不是坐标），核对靠截图的实测尺寸。
sim_rotate_to() {   # <udid> <portrait|landscape> <want_w> <want_h> <设备名>
    local udid="$1" want="$2" w="$3" h="$4" devname="${5:-}" \
          probe="$MATRIX_OUT/_probe/.rotate.png"
    mkdir -p "$MATRIX_OUT/_probe"
    # Device 菜单作用在最前面那个窗口上，而最前面那个未必是我们的。
    [ -z "$devname" ] || sim_focus_window "$devname" >/dev/null 2>&1 || true
    for _ in 1 2 3 4 5; do
        rm -f "$probe"
        xcrun simctl io "$udid" screenshot "$probe" >/dev/null 2>&1
        read -r pw ph <<<"$(matrix::pixels "$probe")"
        [ -n "${pw:-}" ] || return 1
        # 允许 1×/2×/3×：判方向靠长宽比，判具体尺寸交给闸门。
        if { [ "$want" = "portrait"  ] && [ "$ph" -gt "$pw" ]; } || \
           { [ "$want" = "landscape" ] && [ "$pw" -gt "$ph" ]; }; then
            rm -f "$probe"; return 0
        fi
        sim_ax "click menu item \"Rotate Left\" of menu 1 of menu bar item \"Device\" of menu bar 1" >/dev/null
        sleep 2
    done
    echo "   ✗ 转不到 $want（要 ${w}×${h}pt）。Simulator.app 的 Device 菜单" >&2
    echo "     够不着——屏幕锁着，或者这一版 Xcode 的菜单项名字变了。" >&2
    return 1
}

TOTAL=0; SHOT=0; SKIPPED=0; FAILED=0

# 一个 devicetype 建一台专用设备，朝向在同一台上转。
matrix::readlines TIERS < <(matrix::tiers ipad)
matrix::readlines TYPES < <(matrix::tiers ipad | cut -f5 | sort -u)

for DTYPE in "${TYPES[@]}"; do
    [ -n "$DTYPE" ] || continue
    # 这个 devicetype 下、本次要跑的档
    MINE=()
    for line in "${TIERS[@]}"; do
        IFS=$'\t' read -r NAME _P _W _H DT _OR _SP MAN <<<"$line"
        [ "$DT" = "$DTYPE" ] || continue
        [ -z "$MAN" ] || { SKIPPED=$((SKIPPED+1))
            echo "   ⏸ $NAME：分屏档，simctl 摆不出来，见 docs/device-matrix.md"
            matrix::record manual "$NAME" "-" "-" "$_W" "$_H" "" "" "" \
                "分屏要在 Simulator.app 里手工摆"; continue; }
        if [ -n "$ONLY_DEVICES" ] && [[ ",$ONLY_DEVICES," != *",$NAME,"* ]]; then
            continue; fi
        MINE+=("$line")
    done
    [ "${#MINE[@]}" -gt 0 ] || continue

    SIMNAME="$SIM_PREFIX-matrix-$$-$(basename "$DTYPE" | tr -c 'A-Za-z0-9' '-')"
    echo
    echo "══ 专用设备 $SIMNAME ══"
    UDID="$(xcrun simctl create "$SIMNAME" "$DTYPE" "$RUNTIME" 2>/dev/null)"
    if [ -z "$UDID" ]; then
        echo "   ✗ 建不出这台设备（devicetype=$DTYPE runtime=$RUNTIME）" >&2
        FAILED=$((FAILED+1)); continue
    fi
    CREATED+=("$UDID")
    xcrun simctl boot "$UDID" >/dev/null 2>&1 || true
    xcrun simctl bootstatus "$UDID" -b >/dev/null 2>&1 || sleep 10
    xcrun simctl install "$UDID" "$APP" >/dev/null 2>&1 || {
        echo "   ✗ 装不上" >&2; FAILED=$((FAILED+1)); continue; }
    echo "   $UDID"

    if [ "$HEADLESS" = "0" ]; then
        open -a Simulator --args -CurrentDeviceUDID "$UDID" >/dev/null 2>&1 || true
        sleep 4
    fi

    for APPEARANCE in light dark; do
        xcrun simctl ui "$UDID" appearance "$APPEARANCE" >/dev/null 2>&1 || true
        for line in "${MINE[@]}"; do
            IFS=$'\t' read -r NAME _P WANT_W WANT_H _DT ORIENT _SP _MAN <<<"$line"
            xcrun simctl terminate "$UDID" "$BUNDLE_ID" >/dev/null 2>&1 || true
            sleep 1
            if [ "$HEADLESS" = "0" ]; then
                sim_rotate_to "$UDID" "$ORIENT" "$WANT_W" "$WANT_H" "$SIMNAME" || {
                    matrix::record unreachable "$NAME" "-" "$APPEARANCE" \
                        "$WANT_W" "$WANT_H" "" "" "" "转不到 $ORIENT"
                    FAILED=$((FAILED+1)); continue; }
            elif [ "$ORIENT" != "portrait" ]; then
                echo "   ⏸ $NAME：--headless 转不了屏（simctl 无旋转能力）"
                matrix::record manual "$NAME" "-" "$APPEARANCE" \
                    "$WANT_W" "$WANT_H" "" "" "" "--headless 下无法旋转"
                SKIPPED=$((SKIPPED+1)); continue
            fi
            xcrun simctl launch "$UDID" "$BUNDLE_ID" >/dev/null 2>&1 || {
                echo "   ✗ $NAME：App 起不来" >&2
                matrix::record launch-failed "$NAME" "-" "$APPEARANCE" \
                    "$WANT_W" "$WANT_H" "" "" "" "launch 失败"
                FAILED=$((FAILED+1)); continue; }
            sleep 3
            echo "   ▸ $NAME · $APPEARANCE"

            LAST_FILE=""
            for i in $(seq 1 "$N_SCREENS"); do
                SID="${SCREEN_IDS[$((i-1))]}"
                TITLE="${SCREEN_TITLES[$((i-1))]}"
                TOTAL=$((TOTAL+1))

                if [ "$i" -gt 1 ] || [ "$HEADLESS" = "0" ]; then
                    if [ "$HEADLESS" = "1" ]; then
                        echo "   ⏸ $SID：--headless 切不了屏（simctl 无输入能力）"
                        matrix::record manual "$NAME" "$SID" "$APPEARANCE" \
                            "$WANT_W" "$WANT_H" "" "" "" "--headless 无法切屏"
                        SKIPPED=$((SKIPPED+1)); continue
                    fi
                    sim_focus_window "$SIMNAME" >/dev/null 2>&1 || true
                    OUT_AX="$(sim_click_named "$SIMNAME" "$TITLE")"
                    if [[ "$OUT_AX" == *"no-element"* || "$OUT_AX" == *"error"* ]]; then
                        echo "   ✗ $SID：模拟器里点不到名为「$TITLE」的元素。" >&2
                        echo "     辅助功能桥够不着（屏幕锁着？Simulator 没窗口？）," >&2
                        echo "     或者侧栏行的可读名变了。看当前层级：" >&2
                        echo "     osascript -e 'tell application \"System Events\" to tell process \"Simulator\" to get entire contents of (first window whose name starts with \"$SIMNAME\")'" >&2
                        matrix::record switch-failed "$NAME" "$SID" "$APPEARANCE" \
                            "$WANT_W" "$WANT_H" "" "" "" "点不到「$TITLE」"
                        exit 1
                    fi
                    sleep 1.2
                fi

                OUTFILE="$MATRIX_OUT/$(matrix::filename "$NAME" "$SID" "$APPEARANCE")"
                rm -f "$OUTFILE"
                xcrun simctl io "$UDID" screenshot "$OUTFILE" >/dev/null 2>&1
                if [ ! -s "$OUTFILE" ]; then
                    matrix::record launch-failed "$NAME" "$SID" "$APPEARANCE" \
                        "$WANT_W" "$WANT_H" "" "" "" "截图为空"
                    FAILED=$((FAILED+1)); continue
                fi

                # 这一张必须和上一张不同。iPad 没有窗口标题这种独立证据，
                # 这一条是「18 张同一屏」唯一抓得住的地方。
                if [ -n "$LAST_FILE" ] && matrix::same_image "$OUTFILE" "$LAST_FILE"; then
                    echo "   ✗ $SID：这一张和上一屏【逐字节相同】——切换没生效。" >&2
                    matrix::record switch-failed "$NAME" "$SID" "$APPEARANCE" \
                        "$WANT_W" "$WANT_H" "" "" "$OUTFILE" "与上一屏逐字节相同"
                    exit 1
                fi
                LAST_FILE="$OUTFILE"

                read -r PW PH <<<"$(matrix::pixels "$OUTFILE")"
                matrix::record ok "$NAME" "$SID" "$APPEARANCE" \
                    "$WANT_W" "$WANT_H" "$((PW/2))" "$((PH/2))" "$OUTFILE" ""
                SHOT=$((SHOT+1))
            done
        done
    done
done

echo
echo "── iPad 完成 ──"
echo "   走查 $TOTAL 格 · 入矩阵 $SHOT · 跳过 $SKIPPED · 失败 $FAILED"
[ "$TOTAL" -gt 0 ] || { echo "✗ 一格都没走——这不是通过。" >&2; exit 1; }
[ "$FAILED" -eq 0 ] || exit 1
exit 0

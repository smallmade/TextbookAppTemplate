#!/usr/bin/env bash
# [M-C1] 设备矩阵 · Mac 那一半：窗口点数逐档 × 全部画面 × 深浅色。
#
#   bash tools/shots/matrix_mac.sh <输出目录> [--devices a,b] [--screens N]
#
# 通常不直接调，由 tools/shots/device_matrix.sh 调。单独跑得通，是因为
# 「重截某一档」是常事，而为此重跑整个矩阵是一小时。
#
# ## 两条纪律，抄自 walkthrough_mac.sh，一个字都不能松
#
#   * **只按窗口 ID 截图，绝不截屏幕区域。** 这台机器上常年有别的会话、
#     别的 App、负责人自己的东西。区域截图拍到过一次私人视频通话。
#   * **只按辅助功能身份切屏，绝不按坐标点击。** `select row N of outline 1`
#     指的是这个进程里的那个元素；坐标指的是屏幕上的一个点，而屏幕上的
#     东西会动。
#
# ## 第三条，是这个脚本自己加的
#
# walkthrough_mac.sh 的第一版对切屏失败只打印警告、照样截图，结果 18 屏
# 全部切换失败、存下 18 张同一屏的图、打印「完成 18」。**一个分不清「走查
# 了 18 屏」和「给同一屏拍了 18 张」的工具，比没有工具更糟——它产出的是
# 证据。** 所以每切一屏，标题必须是【这一屏该有的那个】才拍。只查「标题
# 变了」不够：它分不出「切到了第 3 屏」和「切到了第 7 屏」。
#
# ## 第四条：行序号不是画面序号
#
# **分节标题也占侧栏的一行。** StructureMechOne 的侧栏是 53 行 = 45 屏 +
# 8 个分节标题；MechanicsOne 是 18 行 = 18 屏，恰好一一对应。原先的
# `select row $i` 把这个巧合当成了规律，在前者身上会从第 4 屏起整体错位，
# 而每一张图都拍得出来、都不是空的，**登记表会是满的**。
#
# 所以按标题找行（matrix::select_screen）：从上一次停下的地方往下选，直到
# 标题变成这一屏该有的那个。分节标题选不动，于是被自然跳过。
#
# ## 拿不到的档
#
# 窗口服务器会把超过可用区的请求钳住。钳住之后截出来的图，证明的是另一台
# 设备上的布局——所以这一档【不产出矩阵格】，只在 _probe/ 里留一张实测图
# 供人看，并在 manifest 里记 unreachable 与实际拿到的点数。伪造一格比缺一
# 格坏得多。
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=matrix_common.sh
source "$ROOT/tools/shots/matrix_common.sh"

MATRIX_ROOT="$ROOT"
MATRIX_OUT="${1:?用法: matrix_mac.sh <输出目录> [--devices a,b] [--screens N]}"
shift || true
ONLY_DEVICES=""; MAX_SCREENS=0
while [ $# -gt 0 ]; do
    case "$1" in
        --devices) ONLY_DEVICES="$2"; shift 2 ;;
        --screens) MAX_SCREENS="$2"; shift 2 ;;
        *) echo "不认识的参数：$1" >&2; exit 2 ;;
    esac
done
matrix::init || exit 1

# 形状全部读 ci.toml 的 [shots]（见 shots_config.py）。这里以前是三行写死的
# MechanicsOne：`build/MechanicsOne.app` / `/private/tmp/mechanicsone-…` /
# `PROC="MechanicsOne"`，于是这套工具在别的项目上只能靠再抄一份来用。
APP_SRC="$ROOT/${SHOTS_MAC_APP:?ci.toml 的 [shots] 没有 mac_app}"
PROC="${SHOTS_MAC_PROCESS:?ci.toml 的 [shots] 没有 mac_process}"
STAGE="/private/tmp/${SHOTS_STAGE_PREFIX:-shots}-device-matrix"
ROWPATH="${SHOTS_AX_ROW_PATH:-outline 1 of scroll area 1 of group 1 of splitter group 1 of group 1 of window 1}"

[ -d "$APP_SRC" ] || {
    echo "✗ 没有 $APP_SRC —— 先 ${SHOTS_MAC_BUILD_HINT:-建出 Mac 成品}" >&2
    exit 2; }
matrix::guard_unlocked || exit 3

BUNDLE_ID="$(plutil -extract CFBundleIdentifier raw \
    "$APP_SRC/Contents/Info.plist" 2>/dev/null)"
[ -n "$BUNDLE_ID" ] || { echo "✗ 读不到 bundle id" >&2; exit 1; }

# ── 画面清单与每一屏该有的标题 ────────────────────────────────────────
matrix::readlines SCREEN_IDS    < <(matrix::screens)
matrix::readlines SCREEN_TITLES < <(matrix::screen_titles)
if [ "${#SCREEN_IDS[@]}" -eq 0 ] || \
   [ "${#SCREEN_IDS[@]}" -ne "${#SCREEN_TITLES[@]}" ]; then
    echo "✗ 画面清单解析不出来：${#SCREEN_IDS[@]} 个 id、${#SCREEN_TITLES[@]} 个 title。" >&2
    echo "  看它读的是什么：python3 tools/shots/shots_config.py --describe" >&2
    echo "  零个画面不是通过。" >&2
    exit 1
fi
N_SCREENS="${#SCREEN_IDS[@]}"
[ "$MAX_SCREENS" -gt 0 ] && [ "$MAX_SCREENS" -lt "$N_SCREENS" ] \
    && N_SCREENS="$MAX_SCREENS"

# ── 收场：把这台机器还原成找到时的样子 ────────────────────────────────
#
# 外观现在走**启动参数**（见 launch_app），所以本轮什么也没往负责人的偏好里
# 写，收场只要关掉 App。上一版往 App 的 defaults 域里写两把键、收场只删一把，
# 于是 `NSRequiresAquaSystemAppearance` 留在那儿——实测确认过残留。这里顺手
# 把两把都清掉，是为了把**以前几轮**留下的残留也带走。
cleanup() {
    defaults delete "$BUNDLE_ID" AppleInterfaceStyle >/dev/null 2>&1 || true
    defaults delete "$BUNDLE_ID" NSRequiresAquaSystemAppearance >/dev/null 2>&1 || true
    pkill -x "$PROC" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

echo "── Mac · 准备可运行的副本（不在 Drive 路径下跑）──"
APP="$(matrix::stage_mac_app "$APP_SRC" "$STAGE")" || {
    echo "✗ 拷贝/重签失败" >&2; exit 1; }
echo "   $APP   bundle=$BUNDLE_ID"

launch_app() {   # <light|dark>
    pkill -x "$PROC" >/dev/null 2>&1 || true
    sleep 1
    # 两种外观都**显式写死**，不要用「删掉这个键」表示浅色。
    #
    # `defaults delete` 的意思是「跟随系统」，而这台机器的系统本身就是深色，
    # 于是浅色那一轮拍到的还是深色——72 对 Mac 截图**逐字节完全相同**，而
    # 登记表报的是 144 格 ok。闸门只查文件名与像素尺寸，不比两张图是不是同
    # 一张，所以一路绿灯。同一天的 iPad 那 4 对是真的不同，正好做对照。
    #
    # ## 为什么用【启动参数】而不是 `defaults write`
    #
    # 上一版把这两把键写进 App 自己的 defaults 域。那对 MechanicsOne 有效，
    # 对 StructureMechOne **完全无效**：三种组合（写 true / 写 Dark / 两把键
    # 都删）拍出来的窗口亮度全是 39，一模一样。也就是说那一款的 630 格里，
    # 315 格「浅色」拍的其实是深色——**和这段注释开头记的那次事故一字不差，
    # 只是换了个原因**，而闸门那一头只查文件名与像素尺寸，仍然一路绿灯。
    #
    # NSUserDefaults 的**参数域优先级最高**，不经 cfprefsd 缓存，两款 App 上
    # 实测都生效（浅色亮度 244–249，深色 39–47）。它还有一个附带好处：
    # 什么都不留在负责人的偏好里。上一版的 cleanup 只删 AppleInterfaceStyle，
    # `NSRequiresAquaSystemAppearance` 是留在那儿的——实测确认过。
    #
    # `NSRequiresAquaSystemAppearance YES` 是让一个 App 无视系统深色、始终用
    # 浅色的那把键，它不依赖系统当前是什么。
    local appearance_args
    if [ "$1" = "dark" ]; then
        appearance_args=(-NSRequiresAquaSystemAppearance NO -AppleInterfaceStyle Dark)
    else
        appearance_args=(-NSRequiresAquaSystemAppearance YES)
    fi
    open -a "$APP" --args "${appearance_args[@]}" || return 1
    local id=""
    for _ in $(seq 1 40); do
        # 按 pid 找，不按 CGWindow 的 owner name —— 后者不一定等于辅助功能
        # 层的进程名（见 matrix_common.sh 的 matrix::window_id）。
        id="$(matrix::window_id "$PROC" || true)"
        [ -n "$id" ] && break
        sleep 0.5
    done
    [ -n "$id" ] || return 1
    echo "$id"
}

ax() { osascript -e "tell application \"System Events\" to tell process \"$PROC\" to $1" 2>/dev/null; }

window_size() {   # → "W H"（点）
    ax "get size of window 1" | tr -d ' ' | tr ',' ' '
}

TOTAL=0; SHOT=0; UNREACHABLE=0; FAILED=0

for APPEARANCE in light dark; do
    echo
    echo "══ 外观：$APPEARANCE ══"
    WINDOW_ID="$(launch_app "$APPEARANCE")" || {
        echo "✗ ${APPEARANCE}：App 起不来或拿不到窗口。它可能被 SIGKILL 了——" >&2
        echo "  看 Console 里的 CODESIGNING。" >&2
        FAILED=$((FAILED+1)); continue; }

    # 最宽裕那块屏的可用区左上角。问不出来就退回 {0,0}，单屏机器上二者相同。
    if ! IFS=$'\t' read -r ORIGIN_X ORIGIN_Y ROOM_W ROOM_H \
            < <(swift "$MATRIX_ROOT/tools/shots/RoomiestScreen.swift" 2>/dev/null); then
        ORIGIN_X=0; ORIGIN_Y=0; ROOM_W=0; ROOM_H=0
    fi
    ORIGIN_X="${ORIGIN_X:-0}"; ORIGIN_Y="${ORIGIN_Y:-0}"
    echo "   屏幕可用区 ${ROOM_W:-?}×${ROOM_H:-?}pt，窗口摆在 {$ORIGIN_X, $ORIGIN_Y}"

    while IFS=$'\t' read -r NAME PLAT WANT_W WANT_H _DT _OR _SP _MAN; do
        [ -n "$NAME" ] || continue
        if [ -n "$ONLY_DEVICES" ] && [[ ",$ONLY_DEVICES," != *",$NAME,"* ]]; then
            continue
        fi

        # 先摆到【最宽裕的那块屏】的可用区左上角，再定尺寸。
        #
        # [M-A20] 这里原本写死 {0, 0}，也就是**主屏**原点。主屏顶上有菜单栏、
        # 底下有程序坞，两者吃掉 90pt，可用高只剩 990——于是要 1010pt 的
        # mac-pro-16 被窗口服务器钳到 990，登记成「本机屏幕放不下」，36 格
        # 证据进了 _probe/。而这台机器的第二块屏没有菜单栏也没有程序坞，满
        # 1080pt：同一个窗口摆 {0,0} 得 1700×990，摆 {1920,0} 得 1700×1010。
        # 要的尺寸一直拿得到，只是没摆对屏。
        #
        # 「够不着」与「摆错屏」在测量结果里长得一模一样（都是被钳矮的高度），
        # 所以这个区别只能在量之前做出来，不能靠事后判读。
        ax "tell window 1 to set position to {$ORIGIN_X, $ORIGIN_Y}" >/dev/null
        ax "tell window 1 to set size to {$WANT_W, $WANT_H}" >/dev/null
        sleep 0.6
        read -r GOT_W GOT_H <<<"$(window_size)"
        GOT_W="${GOT_W:-0}"; GOT_H="${GOT_H:-0}"
        # 窗口 id 会随尺寸变化而变，重新问一次而不是假定。
        WINDOW_ID="$(matrix::window_id "$PROC" || echo "$WINDOW_ID")"

        REACHABLE=1
        if [ "$GOT_W" != "$WANT_W" ] || [ "$GOT_H" != "$WANT_H" ]; then
            REACHABLE=0
            echo "   ⚠ ${NAME}：要 ${WANT_W}×${WANT_H}pt，窗口服务器给 ${GOT_W}×${GOT_H}pt"
            echo "     —— 本机屏幕放不下。这一档不产出矩阵格，只在 _probe/ 留实测图。"
        else
            echo "   ▸ $NAME  ${GOT_W}×${GOT_H}pt"
        fi

        # 侧栏的行序号从头开始数。分节标题也占行，所以「第 i 屏」不等于
        # 「第 i 行」——matrix::select_screen 按标题往下找，把标题行跳过去。
        MATRIX_ROW=1
        N_ROWS="$(matrix::rows "$PROC" "$ROWPATH")"
        if [ "$N_ROWS" -lt "$N_SCREENS" ]; then
            echo "   ✗ 侧栏只有 $N_ROWS 行，而画面有 $N_SCREENS 屏。" >&2
            echo "     辅助功能路径可能不对：$ROWPATH" >&2
            exit 1
        fi
        for i in $(seq 1 "$N_SCREENS"); do
            SID="${SCREEN_IDS[$((i-1))]}"
            WANT_TITLE="${SCREEN_TITLES[$((i-1))]}"
            TOTAL=$((TOTAL+1))

            if ! matrix::select_screen "$PROC" "$ROWPATH" "$WANT_TITLE" "$N_ROWS"; then
                echo "   ✗ 第 $i 屏（${SID}）：扫到第 $N_ROWS 行也没出现标题「${WANT_TITLE}」。" >&2
                echo "     最后看到的是「${MATRIX_LAST_TITLE:-}」。辅助功能层级可能变了：" >&2
                echo "     osascript -e 'tell application \"System Events\" to tell process \"$PROC\" to get entire contents of window 1'" >&2
                matrix::record switch-failed "$NAME" "$SID" "$APPEARANCE" \
                    "$WANT_W" "$WANT_H" "$GOT_W" "$GOT_H" "" \
                    "找不到标题「${WANT_TITLE}」，停在「${MATRIX_LAST_TITLE:-}」"
                exit 1
            fi

            if [ "$REACHABLE" = "1" ]; then
                OUTFILE="$MATRIX_OUT/$(matrix::filename "$NAME" "$SID" "$APPEARANCE")"
            else
                mkdir -p "$MATRIX_OUT/_probe"
                # 探针名里【没有设备名】——闸门按「三段都在文件名里」找格，
                # 带上设备名会把一张钳过尺寸的图算成那一格的证据。
                OUTFILE="$MATRIX_OUT/_probe/probe-w${GOT_W}h${GOT_H}-${SID}-${APPEARANCE}.png"
            fi
            rm -f "$OUTFILE"
            # -l<id> 是窗口截图。永远不用 -R（屏幕区域）。-o 去掉阴影，
            # 于是像素正好是点数 ×（屏幕倍率）。
            screencapture -l"$WINDOW_ID" -o "$OUTFILE" 2>/dev/null

            if [ ! -s "$OUTFILE" ]; then
                matrix::record launch-failed "$NAME" "$SID" "$APPEARANCE" \
                    "$WANT_W" "$WANT_H" "$GOT_W" "$GOT_H" "" "截图为空"
                FAILED=$((FAILED+1)); continue
            fi
            if [ "$REACHABLE" = "1" ]; then
                matrix::record ok "$NAME" "$SID" "$APPEARANCE" \
                    "$WANT_W" "$WANT_H" "$GOT_W" "$GOT_H" "$OUTFILE" ""
                SHOT=$((SHOT+1))
            else
                matrix::record unreachable "$NAME" "$SID" "$APPEARANCE" \
                    "$WANT_W" "$WANT_H" "$GOT_W" "$GOT_H" "$OUTFILE" \
                    "本机屏幕放不下，钳到 ${GOT_W}×${GOT_H}pt"
                UNREACHABLE=$((UNREACHABLE+1))
            fi
        done
    done < <(matrix::tiers mac)
done

# ── 采集自己查一遍：深浅色不许是同一张 ────────────────────────────────
#
# 闸门 check_device_matrix.py 也查这一条，但它**不一定跑得到**：一个项目的
# 画面清单形状它还不认识时，它退 2 变成一行黄色的跳过，而这一轮的 630 张图
# 照样躺在目录里，看起来像证据。
#
# 「拍完之后没人查」和「查过了是对的」必须分得开，所以采集这一头自己查，
# 判据用文件哈希（matrix::same_image），和闸门那一头是同一条。
IDENTICAL=0
for pair in $(ls "$MATRIX_OUT"/*__light.png 2>/dev/null); do
    dark="${pair%__light.png}__dark.png"
    matrix::same_image "$pair" "$dark" || continue
    IDENTICAL=$((IDENTICAL+1))
    [ "$IDENTICAL" -le 5 ] && echo "   ✗ $(basename "${pair%__light.png}")：深浅色逐字节相同" >&2
done

echo
echo "── Mac 完成 ──"
echo "   走查 $TOTAL 格 · 入矩阵 $SHOT · 本机放不下 $UNREACHABLE · 失败 $FAILED"
# 零个不是通过。
[ "$TOTAL" -gt 0 ] || { echo "✗ 一格都没走——这不是通过。" >&2; exit 1; }
if [ "$IDENTICAL" -gt 0 ]; then
    echo "✗ $IDENTICAL 个格位的深色与浅色是**同一张图**——那一半不是证据。" >&2
    echo "  先确认外观参数对这个 App 真的生效：" >&2
    echo "  open -a <app> --args -NSRequiresAquaSystemAppearance YES  应当是浅色的" >&2
    exit 1
fi
[ "$FAILED" -eq 0 ] || exit 1
exit 0

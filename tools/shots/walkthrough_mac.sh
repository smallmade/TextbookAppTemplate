#!/usr/bin/env bash
# [E-09] 打开成品里的每一个画面，逐屏拍一张。
#
#   bash tools/shots/walkthrough_mac.sh [输出目录]
#
# A-01 是拿一段随手写的片段做的，片段没留下来，于是 E-09 从重写它开始。
# 这就是它成为一个文件的理由：走查不是一次性的事，画面一加就要再走一遍，
# 而每次凭记忆重做的东西，每次做出来都不一样。
#
# ## 它要守的纪律（engineering-standard.md §5m）
#
#   * **绝不截屏幕区域，只按 CGWindowID 截窗口。** 区域截图会拍到这台机器
#     上别的东西——别的会话、别的 App、负责人自己的工作。
#   * **绝不按坐标点击。** 切屏是请 System Events 在**这个进程内**
#     `select row N of outline 1`，那是按辅助功能身份定位；坐标指的是屏幕上
#     的一个点，而屏幕上的东西会动。
#   * **切屏要核对。** 第一版对切屏失败只打印警告、照样截图，于是 18 次切换
#     全部失败、存下 18 张同一屏的图、打印「完成」。一个分不清「走查了 18 屏」
#     和「给同一屏拍了 18 张」的工具，比没有工具更糟——它产出的是证据。
#
# ## 为什么先把 .app 拷出项目目录
#
# 在原地启动会被内核 SIGKILL（`CODESIGNING / Invalid Page`）：项目在
# Google Drive 的 File Provider 挂载点上，loader 映回来的页与它验过的页不是
# 同一批。拷到本地盘并 ad-hoc 重签即可。记为缺陷 53。
#
# ## 项目形状读 ci.toml
#
# 这个脚本原先把 `MechanicsOne` 写死在七处（落地目录、进程名、.app 名、
# RootView 的路径……），于是它在别的项目上只能靠再抄一份来用。抄一份的代价
# 见 shots_config.py 开头。
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=matrix_common.sh
source "$ROOT/tools/shots/matrix_common.sh"
MATRIX_ROOT="$ROOT"
matrix::load_config || exit 1

OUT="${1:-$ROOT/build/walkthrough}"
APP_SRC="$ROOT/${SHOTS_MAC_APP:?ci.toml 的 [shots] 没有 mac_app}"
PROC="${SHOTS_MAC_PROCESS:?ci.toml 的 [shots] 没有 mac_process}"
STAGE="/private/tmp/${SHOTS_STAGE_PREFIX:-shots}-walkthrough"
ROWPATH="${SHOTS_AX_ROW_PATH:-outline 1 of scroll area 1 of group 1 of splitter group 1 of group 1 of window 1}"

if [ ! -d "$APP_SRC" ]; then
    echo "先建出 $APP_SRC:  ${SHOTS_MAC_BUILD_HINT:-（见 tools/build/）}" >&2
    exit 2
fi

# 锁屏时 System Events 对一个【真在跑】的进程报「0 windows」，看起来和脚本
# bug、和跨会话抢窗口一模一样。先查这一条。
matrix::guard_unlocked || exit 3

echo "── 准备可运行的副本（不在 Drive 路径下跑）──"
mkdir -p "$OUT"
APP="$(matrix::stage_mac_app "$APP_SRC" "$STAGE")" || {
    echo "✗ 拷贝/重签失败" >&2; exit 1; }
echo "   $APP"

pkill -x "$PROC" 2>/dev/null || true
sleep 1
open -a "$APP"

# 窗口得先存在才能被指着。用轮询而不是固定 sleep：冷启动一个刚拷过来的包
# 和热启动不是一回事，而固定 sleep 只会被调成先发生的那一种。
echo "── 等窗口出现 ──"
WINDOW_ID=""
for _ in $(seq 1 40); do
    WINDOW_ID="$(matrix::window_id "$PROC" || true)"
    [ -n "$WINDOW_ID" ] && break
    sleep 0.5
done
if [ -z "$WINDOW_ID" ]; then
    echo "找不到 $PROC 的窗口。它可能被 SIGKILL 了——看 Console 里的 CODESIGNING" >&2
    exit 1
fi
echo "   CGWindowID = $WINDOW_ID"

# 把窗口拉到显示器允许的最高，好让每一张都尽量多显示一些读数列。窗口服务器
# 会把它钳到可用高度——这是「有多少用多少」的请求，不是一个要和某块屏幕保持
# 同步的数字。设尺寸同样是按元素定位，没有用到任何坐标。
osascript -e "tell application \"System Events\" to tell process \"$PROC\" \
    to tell window 1 to set position to {0, 0}" >/dev/null 2>&1 || true
osascript -e "tell application \"System Events\" to tell process \"$PROC\" \
    to tell window 1 to set size to {1460, 2200}" >/dev/null 2>&1 || true
sleep 1
# 窗口 id 会随尺寸变化而变，重新问一次而不是假定。
WINDOW_ID="$(matrix::window_id "$PROC" || echo "$WINDOW_ID")"

matrix::readlines SCREEN_IDS    < <(matrix::screens)
matrix::readlines SCREEN_TITLES < <(matrix::screen_titles)
COUNT="${#SCREEN_IDS[@]}"
if [ "$COUNT" -eq 0 ] || [ "$COUNT" -ne "${#SCREEN_TITLES[@]}" ]; then
    echo "✗ 画面清单解析不出来：$COUNT 个 id、${#SCREEN_TITLES[@]} 个 title。" >&2
    echo "  看它读的是什么：python3 tools/shots/shots_config.py --describe" >&2
    exit 1
fi

N_ROWS="$(matrix::rows "$PROC" "$ROWPATH")"
echo "── 逐屏走查（$COUNT 屏，侧栏 $N_ROWS 行）──"
if [ "$N_ROWS" -lt "$COUNT" ]; then
    echo "✗ 侧栏只有 $N_ROWS 行，而画面有 $COUNT 屏。辅助功能路径可能不对：" >&2
    echo "  $ROWPATH" >&2
    exit 1
fi

MATRIX_ROW=1
FAILED=0
for i in $(seq 1 "$COUNT"); do
    SID="${SCREEN_IDS[$((i-1))]}"
    WANT_TITLE="${SCREEN_TITLES[$((i-1))]}"
    # 按标题找行，不按序号算行：**分节标题也占一行**，两者只在恰好没有分节
    # 的 App 上重合。见 matrix_common.sh 的 matrix::select_screen。
    if ! matrix::select_screen "$PROC" "$ROWPATH" "$WANT_TITLE" "$N_ROWS"; then
        echo "   ✗ 第 $i 屏（${SID}）：扫到第 $N_ROWS 行也没出现标题「${WANT_TITLE}」。" >&2
        echo "     最后看到的是「${MATRIX_LAST_TITLE:-}」。辅助功能层级可能变了：" >&2
        echo "     osascript -e 'tell application \"System Events\" to tell process \"$PROC\" to get entire contents of window 1'" >&2
        FAILED=1
        break
    fi
    screencapture -l"$WINDOW_ID" -o "$OUT/$(printf '%02d' "$i")-$SID.png"
    printf '   %02d  %-30s %s\n' "$i" "$SID" "$MATRIX_TITLE"
done

echo "── 完成，图在 $OUT ──"
ls "$OUT" | wc -l
exit "$FAILED"

#!/usr/bin/env bash
# [C-03] 按 ASC 接受的像素尺寸拍 Mac 商店截图，挑几屏有深度的。
#
#   bash tools/shots/capture_mac_asc_sizes.sh [输出目录]
#
# 纪律和 walkthrough_mac.sh 一样（engineering-standard.md §5m）：只按
# CGWindowID 截窗口，只按辅助功能身份切屏，绝不用屏幕坐标。
#
# ⚠ 需要解锁的会话。锁屏时 System Events 对一个【真在跑】的进程报
# 「0 windows」，看起来和脚本 bug、和跨会话抢窗口一模一样。先查：
# `ioreg -n Root -d1 -a | plutil -p - | grep CGSSessionScreenIsLocked`
#
# ## 为什么只出一个尺寸，不是四个
#
# 规范 §8 的那四个数（1280x800 / 1440x900 / 2560x1600 / 2880x1800）是 ASC
# 接受的**交付 PNG 的像素**尺寸——开发者挑一个，整套按它交，不是一个尺寸
# 交一张。挑哪一个是项目自己的事（有的 App 有三栏布局，最小窗口拿不到小
# 的那两档），所以它写在 ci.toml 的 [shots]：`asc_size` 与 `asc_window`。
#
# ## 挑哪几屏，也是项目自己的事
#
# 以前这里是一张写死的 `行号:名字` 表。行号会随侧栏增删而错位，而错位之后
# 每一张图都拍得出来、都不是空的——**只是拍的是别的屏**。现在写的是画面 id
# （ci.toml 的 `asc_screens`），行由标题去找。
#
# 一项可以写成 `<画面 id>:<交付文件名>`。交付文件名是商店那一头的事（已经
# 交过一轮的名字不必因为内部 id 变了就跟着改），省掉冒号就用 id 当文件名。
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=matrix_common.sh
source "$ROOT/tools/shots/matrix_common.sh"
MATRIX_ROOT="$ROOT"
matrix::load_config || exit 1

OUT="${1:-$ROOT/submission/screenshots/mac}"
APP_SRC="$ROOT/${SHOTS_MAC_APP:?ci.toml 的 [shots] 没有 mac_app}"
PROC="${SHOTS_MAC_PROCESS:?ci.toml 的 [shots] 没有 mac_process}"
STAGE="/private/tmp/${SHOTS_STAGE_PREFIX:-shots}-asc"
ROWPATH="${SHOTS_AX_ROW_PATH:-outline 1 of scroll area 1 of group 1 of splitter group 1 of group 1 of window 1}"
SIZE="${SHOTS_ASC_SIZE:?ci.toml 的 [shots] 没有 asc_size（如 2560x1600）}"
read -r WINDOW_W WINDOW_H <<<"${SHOTS_ASC_WINDOW:?ci.toml 的 [shots] 没有 asc_window（如 [1280, 800]）}"
WANT_IDS="${SHOTS_ASC_SCREENS:?ci.toml 的 [shots] 没有 asc_screens}"

if [ ! -d "$APP_SRC" ]; then
    echo "先建出 $APP_SRC:  ${SHOTS_MAC_BUILD_HINT:-（见 tools/build/）}" >&2
    exit 2
fi
matrix::guard_unlocked || exit 3

# 挑的那几屏，标题从画面清单里查——不另抄一份。
matrix::readlines SCREEN_IDS    < <(matrix::screens)
matrix::readlines SCREEN_TITLES < <(matrix::screen_titles)
title_of() {   # <画面 id> → 标题；查不到退 1
    local i
    for i in $(seq 1 "${#SCREEN_IDS[@]}"); do
        if [ "${SCREEN_IDS[$((i-1))]}" = "$1" ]; then
            echo "${SCREEN_TITLES[$((i-1))]}"; return 0
        fi
    done
    return 1
}
for entry in $WANT_IDS; do
    title_of "${entry%%:*}" >/dev/null || {
        echo "✗ asc_screens 里的「${entry%%:*}」不是本 App 的画面 id。" >&2
        echo "  现有的：${SCREEN_IDS[*]}" >&2
        exit 1; }
done

echo "── 准备可运行的副本（不在 Drive 路径下跑）──"
mkdir -p "$OUT/$SIZE"
APP="$(matrix::stage_mac_app "$APP_SRC" "$STAGE")" || {
    echo "✗ 拷贝/重签失败" >&2; exit 1; }

pkill -x "$PROC" 2>/dev/null || true
sleep 1
open -a "$APP"

echo "── 等窗口出现，设成 ${WINDOW_W}x${WINDOW_H}pt（→ ${SIZE}px）──"
WINDOW_ID=""
for _ in $(seq 1 40); do
    WINDOW_ID="$(matrix::window_id "$PROC" || true)"
    [ -n "$WINDOW_ID" ] && break
    sleep 0.5
done
[ -n "$WINDOW_ID" ] || { echo "找不到 $PROC 的窗口" >&2; exit 1; }

osascript -e "tell application \"System Events\" to tell process \"$PROC\" \
    to tell window 1 to set position to {0, 0}" >/dev/null 2>&1 || true
osascript -e "tell application \"System Events\" to tell process \"$PROC\" \
    to tell window 1 to set size to {$WINDOW_W, $WINDOW_H}" >/dev/null 2>&1 || true
sleep 1
WINDOW_ID="$(matrix::window_id "$PROC" || echo "$WINDOW_ID")"

N_ROWS="$(matrix::rows "$PROC" "$ROWPATH")"
MATRIX_ROW=1
for entry in $WANT_IDS; do
    id="${entry%%:*}"
    name="${entry#*:}"; [ "$name" = "$entry" ] && name="$id"
    WANT_TITLE="$(title_of "$id")"
    # 每一屏都从第 1 行重扫：asc_screens 的顺序不必是侧栏顺序。
    MATRIX_ROW=1
    if ! matrix::select_screen "$PROC" "$ROWPATH" "$WANT_TITLE" "$N_ROWS"; then
        echo "✗ $id：扫到第 $N_ROWS 行也没出现标题「$WANT_TITLE」。" >&2
        exit 1
    fi

    OUTFILE="$OUT/$SIZE/$name.png"
    rm -f "$OUTFILE"
    screencapture -l"$WINDOW_ID" -o "$OUTFILE" 2>/dev/null || true
    ACTUAL="$(sips -g pixelWidth -g pixelHeight "$OUTFILE" 2>/dev/null \
        | awk '/pixelWidth/{w=$2} /pixelHeight/{h=$2} END{print w"x"h}' || true)"
    if [ "$ACTUAL" != "$SIZE" ]; then
        echo "✗ $id：要求 $SIZE，实测 $ACTUAL" >&2
        exit 1
    fi
    printf "   %-28s %s  ✓\n" "$MATRIX_TITLE" "$ACTUAL"
done

echo "── 完成，图在 $OUT/$SIZE ──"
ls "$OUT/$SIZE"

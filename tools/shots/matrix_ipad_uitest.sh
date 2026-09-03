#!/bin/bash
# [M-A21] The iPad half of the device matrix, driven by XCUITest.
#
#   bash tools/shots/matrix_ipad_uitest.sh <输出目录> [--devices a,b]
#
# ## 为什么不是 matrix_ipad.sh 那条路
#
# 那一条从来没有可能成功，2026-09-03 实测：它把 Mac 那套「System Events 点侧栏行」
# 原样搬来对着 Simulator 进程用，而 ①ci.toml 的 ax_row_path 在 Simulator 里根本
# 取不到（报 Invalid index，那是 macOS 版侧栏的路径）；②它靠 `title of window 1`
# 判断切到了哪一屏，而 Simulator 的窗口标题是**设备名**，永远不含画面标题。
# 根因是 iOS App 的辅助功能元素不经由 macOS System Events 暴露——探一个活着的
# Simulator 窗口，里面只有模拟器自己的 AXButton/AXGroup/AXToolbar。
#
# 更要紧的是：那条路**送键给当前最前面的那个 App**。实测往模拟器送四次下箭头，
# 截图纹丝不动，回头一查最前面的是负责人的编辑器——键落进了别人的文档。这台
# 机器常年几十个会话并行，任何「先 activate 再送键」的采集都会这样。
#
# XCUITest 直接对着模拟器里的 App 说话，既不需要也偷不到窗口焦点；而且每一下
# 都是真实触摸，没有任何开关预设画面——架构不变量 4 要的正是这个。
#
# ## 一次性的 Xcode 工程
#
# XCUITest 必须有 .xcodeproj，而本仓库刻意只有 SwiftPM。所以工程是**生成的**：
# xcodegen 按 ipad-uitest/project.yml 现做一个，用完即弃，且它**不构建 App**
# ——被拍的就是矩阵刚装上去的那个二进制，另建一份等于拍了另一个构建。
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
source "$HERE/matrix_common.sh"
MATRIX_ROOT="$ROOT"

MATRIX_OUT="${1:?用法: matrix_ipad_uitest.sh <输出目录> [--devices a,b]}"; shift
ONLY_DEVICES=""
while [ $# -gt 0 ]; do
    case "$1" in
        --devices) ONLY_DEVICES="$2"; shift 2 ;;
        *) echo "不认识的参数：$1" >&2; exit 2 ;;
    esac
done
# 绝对化。xcodebuild 那一步跑在 `( cd "$UITEST_DIR" && … )` 的子 shell 里，
# 相对的 -resultBundlePath / 日志路径会落到 uitest 目录下（或者根本落不下）——
# **这就是此前每一次 driver 运行都失败、而手工运行都通过的全部原因**：手工那两次
# 传的是绝对路径。失败现场看起来像编译错误，因为结果包压根没产出。
MATRIX_OUT="$(cd "$(dirname "$MATRIX_OUT")" 2>/dev/null && pwd)/$(basename "$MATRIX_OUT")"
matrix::init || exit 1

# DerivedData **绝不放在仓库里**。仓库在 Google Drive 上，File Provider 会给
# 构建产物补 FinderInfo，codesign 当场报错——施工书 §8「中间产物绝不放
# Google Drive」说的就是这件事。把 -derivedDataPath 指到 $MATRIX_OUT 下面的那
# 一版，十六轮全部死在 `Command CodeSign failed with a nonzero exit code`，
# 而手工那两轮用的是 Xcode 默认位置（在 ~/Library 下，不在 Drive 上），所以通过。
MATRIX_DERIVED="${TMPDIR:-/tmp}matrix-uitest-derived-$$"
mkdir -p "$MATRIX_DERIVED"
trap 'rm -rf "$MATRIX_DERIVED"' EXIT

UITEST_DIR="$HERE/ipad-uitest"
# 形状全部读 ci.toml（--shell 把它们导成环境变量），不在这里写死任何一款 App。
eval "$(python3 "$HERE/shots_config.py" --root "$MATRIX_ROOT" --shell)"
IPAD_APP="$MATRIX_ROOT/${SHOTS_IPAD_APP:?ci.toml 没有 ipad_app}"
[ -d "$IPAD_APP" ] || {
    echo "✗ 找不到 iPad 包：$IPAD_APP" >&2
    echo "  先建：${SHOTS_IPAD_BUILD_HINT:-见 ci.toml}" >&2; exit 1; }
# bundle id 从包自己的 Info.plist 读——写死一个就等于把某一款 App 焊进共用脚本。
BUNDLE_ID="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' \
    "$IPAD_APP/Info.plist" 2>/dev/null)"
[ -n "$BUNDLE_ID" ] || { echo "✗ 读不出 CFBundleIdentifier：$IPAD_APP" >&2; exit 1; }

SCREEN_PAIRS="$(paste -d: \
    <(python3 "$HERE/shots_config.py" --root "$MATRIX_ROOT" --screens) \
    <(python3 "$HERE/shots_config.py" --root "$MATRIX_ROOT" --screen-titles) \
    | paste -sd'|' -)"
[ -n "$SCREEN_PAIRS" ] || { echo "✗ 画面清单是空的" >&2; exit 1; }

TOTAL=0; SHOT=0; FAILED=0
while IFS=$'\t' read -r NAME PLAT WANT_W WANT_H DEVTYPE ORIENT SPLIT MANUAL; do
    [ -n "$NAME" ] || continue
    [ "$PLAT" = "ipad" ] || continue
    if [ -n "$ONLY_DEVICES" ] && [[ ",$ONLY_DEVICES," != *",$NAME,"* ]]; then continue; fi
    if [ -n "$SPLIT" ]; then
        echo "   ⏸ $NAME：分屏档，XCUITest 也摆不出来，仍需人手一次"
        for SID in $(python3 "$HERE/shots_config.py" --root "$MATRIX_ROOT" --screens); do
            for AP in light dark; do
                TOTAL=$((TOTAL+1))
                matrix::record manual "$NAME" "$SID" "$AP" "$WANT_W" "$WANT_H" "" "" "" \
                    "分屏档：simctl 与 XCUITest 都摆不出并排两个 App"
            done
        done
        continue
    fi

    echo
    echo "══ $NAME（$DEVTYPE · $ORIENT）══"
    # 专用设备：这台机器上常年开着别的会话的模拟器，`booted` 会挑到别人那台。
    DEV_NAME="matrix-$$-$NAME"
    UDID="$(xcrun simctl create "$DEV_NAME" "$DEVTYPE" 2>/dev/null)"
    if [ -z "$UDID" ]; then
        echo "   ✗ 建不出设备（devicetype 不存在？）：$DEVTYPE" >&2
        FAILED=$((FAILED+1)); continue
    fi
    xcrun simctl boot "$UDID" >/dev/null 2>&1
    # 等它真的起来，而不是数秒。八秒够不够取决于这台机器同时开着几台模拟器，
    # 而这里常年开着别的会话的五六台——数秒的那一版在忙的时候整档整档地失败，
    # 失败方式还是 xcodebuild 连结果包都来不及产出，看起来像编译错误。
    xcrun simctl bootstatus "$UDID" -b >/dev/null 2>&1 || sleep 20
    xcrun simctl install "$UDID" "$IPAD_APP" >/dev/null 2>&1 || {
        echo "   ✗ 装不进去" >&2; FAILED=$((FAILED+1))
        xcrun simctl delete "$UDID" >/dev/null 2>&1; continue; }

    # 工程一档生成一次，**不是一个外观生成一次**。放在外观循环里的那一版
    # 每跑一次就把 .xcodeproj 重写一遍，而 DerivedData 里还留着上一次生成
    # 的那一份构建——十六轮全败，且败在 xcodebuild 连结果包都产不出来，
    # 看起来像编译错误。手工只生成一次、只跑一次的那两轮恰好都通过了。
    # 深浅色不影响工程、只影响模拟器，本来就不该在这里重来。
    python3 - "$UITEST_DIR" "$SCREEN_PAIRS" "$ORIENT" "$BUNDLE_ID" <<'PY'
import sys
from pathlib import Path
d, pairs, orient, bundle = Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
spec = (d / "project.yml").read_text(encoding="utf-8")
for token, value in (("__MATRIX_SCREENS__", pairs),
                     ("__MATRIX_ORIENTATION__", orient),
                     ("__MATRIX_BUNDLE_ID__", bundle)):
    spec = spec.replace(token, value)
(d / "project.generated.yml").write_text(spec, encoding="utf-8")
PY
    ( cd "$UITEST_DIR" && xcodegen generate --spec project.generated.yml --quiet ) || {
        echo "   ✗ xcodegen 生成失败" >&2; FAILED=$((FAILED+1))
        xcrun simctl delete "$UDID" >/dev/null 2>&1; continue; }

    for AP in light dark; do
        xcrun simctl ui "$UDID" appearance "$AP" >/dev/null 2>&1
        # 先杀掉再启动。`simctl launch` 对一个已经在跑的 App 只是把它调到前台，
        # 不重启——于是深色这一轮开在浅色那一轮停下的地方（最后一屏
        # 「Axial & Thermal」），而侧栏是关的。四个横屏档的 dark 全败在这里，
        # 且是被那句「要 X，屏上是 Y」的校验拦下的：没有它，18 张会以错误的
        # 名字存进矩阵，每一张看起来都很正常。
        xcrun simctl terminate "$UDID" "$BUNDLE_ID" >/dev/null 2>&1 || true
        sleep 1
        xcrun simctl launch "$UDID" "$BUNDLE_ID" >/dev/null 2>&1
        sleep 3

        RESULT="$MATRIX_OUT/_xcresult/$NAME-$AP.xcresult"
        rm -rf "$RESULT"; mkdir -p "$(dirname "$RESULT")"
        # 日志留下来。上一版把 xcodebuild 的输出丢进 /dev/null，于是十六轮
        # 失败只留下「未通过」三个字，而原因就写在那些被丢掉的输出里。
        LOG="$MATRIX_OUT/_log/$NAME-$AP.txt"; mkdir -p "$(dirname "$LOG")"
        if ( cd "$UITEST_DIR" && xcodebuild test \
                -project MatrixUITests.xcodeproj -scheme MatrixUITests \
                -destination "id=$UDID" -resultBundlePath "$RESULT" \
                -derivedDataPath "$MATRIX_DERIVED" \
                >"$LOG" 2>&1 ); then
            ATT="$MATRIX_OUT/_att/$NAME-$AP"; rm -rf "$ATT"
            xcrun xcresulttool export attachments --path "$RESULT" \
                --output-path "$ATT" >/dev/null 2>&1
            if python3 "$UITEST_DIR/extract_cells.py" "$ATT" "$MATRIX_OUT" "$NAME" "$AP"; then
                for SID in $(python3 "$HERE/shots_config.py" --root "$MATRIX_ROOT" --screens); do
                    TOTAL=$((TOTAL+1))
                    F="$MATRIX_OUT/$(matrix::filename "$NAME" "$SID" "$AP")"
                    if [ -s "$F" ]; then
                        matrix::record ok "$NAME" "$SID" "$AP" "$WANT_W" "$WANT_H" \
                            "$WANT_W" "$WANT_H" "$F" "XCUITest"
                        SHOT=$((SHOT+1))
                    else
                        matrix::record launch-failed "$NAME" "$SID" "$AP" \
                            "$WANT_W" "$WANT_H" "" "" "" "测试通过但这一格没落盘"
                        FAILED=$((FAILED+1))
                    fi
                done
            else
                echo "   ✗ $AP：附件里一格都没取出来" >&2; FAILED=$((FAILED+1))
            fi
        else
            echo "   ✗ $AP：xcodebuild test 未通过" >&2
            grep -E "error:|failed -" "$LOG" | tail -3 | sed 's/^/     /' >&2
            FAILED=$((FAILED+1))
        fi
    done

    xcrun simctl shutdown "$UDID" >/dev/null 2>&1
    xcrun simctl delete "$UDID" >/dev/null 2>&1
done < <(matrix::tiers ipad)

echo
echo "── iPad（XCUITest）完成 ──"
echo "   走查 $TOTAL 格 · 入矩阵 $SHOT · 失败 $FAILED"
[ "$FAILED" -eq 0 ]

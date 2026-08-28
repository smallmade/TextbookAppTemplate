#!/bin/bash
# 商店截图 —— 脚本驱动【真实交互】。
#
#   bash capture_ios.sh <udid> <bundle-id> <输出目录>
#
# **不用运行时钩子。** 自动化截图的老路线是在 App 里留一个环境变量开关，
# 启动时预设界面状态（PlotOne 的 QAHooks 就是这么来的）——那导致了
# Guideline 5.6 账号层拒审。代价不是一次重新提交。
#
# 这个脚本改用真实交互：点击、输入、选择，和用户做的事一模一样。它慢一些、
# 需要为每款 App 写一段坐标序列，但出货二进制里不会留下任何开关。
#
# 用法：把你的点击序列写进下面的 STEPS，每行 `tap x y` 或 `wait 秒` 或
# `shot 名称`。坐标从 `xcrun simctl io <udid> screenshot` 出来的图上量。
set -uo pipefail
UDID="${1:-}"; BUNDLE="${2:-}"; OUT="${3:-shots}"
[ -n "$UDID" ] && [ -n "$BUNDLE" ] || {
    echo "用法: bash capture_ios.sh <udid> <bundle-id> [输出目录]" >&2; exit 2; }
mkdir -p "$OUT"

STEPS_FILE="${STEPS_FILE:-$(dirname "${BASH_SOURCE[0]}")/steps.txt}"
[ -f "$STEPS_FILE" ] || { echo "缺少步骤文件：$STEPS_FILE" >&2
    echo "格式：每行 'tap x y' / 'wait 秒' / 'shot 名称'" >&2; exit 2; }

echo "==> 启动 $BUNDLE"
xcrun simctl launch "$UDID" "$BUNDLE" >/dev/null || exit 1
sleep 2

n=0
while read -r cmd a b; do
    case "$cmd" in
        ""|\#*) ;;
        tap)  # 真实点击。没有别的路径——不接受任何形式的状态预设。
              xcrun simctl ui "$UDID" tap "$a" "$b" 2>/dev/null \
                || echo "  （本机 simctl 不支持 tap，请用 Xcode UI 测试或手工）" ;;
        wait) sleep "$a" ;;
        shot) n=$((n+1))
              f="$OUT/$(printf '%02d' $n)-${a}.png"
              xcrun simctl io "$UDID" screenshot "$f" >/dev/null 2>&1 \
                && echo "  ✓ $f" ;;
    esac
done < "$STEPS_FILE"
echo "==> 共 $n 张。下一步：python tools/shots/resize_for_asc.py $OUT out/"

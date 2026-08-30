#!/bin/bash
# Gate S 全六项 —— 一条命令跑完。
#
#   bash tools/ci/run_gate_s.sh
#
# check_binary_hygiene.sh 跑一次只查得到一半：对源码目录跑 S-1..3，对成品包
# 跑 S-4..6。规范说的是「六项检查**全数**通过」，而它自己的结尾也提醒过
# 「两次都跑过才算」。这个脚本把两次串起来，并且在中间**真的把包做出来**：
#
#     建 release → 装配 .app → strip → 签名 → 查
#
# 中间那几步不是顺带的。它们本身就在验：
#
#   * **装配**验的是资源到底进没进包。曾经没进——App 一直在从构建目录的
#     绝对路径读正典，装配出来的 .app 换台机器就会 trap。
#   * **strip** 验的是产物形状和出货一致。未 strip 的二进制带一整张调试
#     映射，S-4 会被构建期路径淹没。
#   * **签名**验的是包结构合法。曾经不合法——资源包被放进了 Contents/MacOS，
#     codesign 整包拒签，而**一个签不了名的 App 是投递不出去的**。
#
# 这里用的是 ad-hoc 签名（`-`），只为把 S-6 的路径走通。真正的分发签名在
# 阶段 08，用 App Store 描述文件。
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

RED=$'\033[31m'; GREEN=$'\033[32m'; BOLD=$'\033[1m'; OFF=$'\033[0m'
FAILED=0

echo "${BOLD}Gate S · 六项全跑${OFF}"
echo

echo "${BOLD}[1/4] 建 release${OFF}"
swift build --package-path swift -c release >/dev/null 2>&1 \
    || { echo "${RED}release 构建失败${OFF}"; exit 1; }
echo "  ${GREEN}✓${OFF} 零警告（-warnings-as-errors）"

echo
echo "${BOLD}[2/4] 装配并 strip${OFF}"
rm -rf build/MechanicsOne.app
APP="$(bash tools/build/make_app.sh release)" \
    || { echo "${RED}装配失败${OFF}"; exit 1; }
[ -f "$APP/Contents/Resources/specification.json" ] \
    || { echo "${RED}✗ 出货正典没进包${OFF}"; exit 1; }
echo "  ${GREEN}✓${OFF} 正典在 Contents/Resources 里"

echo
echo "${BOLD}[3/4] ad-hoc 签名${OFF}"
codesign --force --sign - --entitlements swift/App/MechanicsOne.entitlements \
         "$APP" >/dev/null 2>&1 \
    || { echo "${RED}✗ 签不了名 —— 包结构不合法，投递不出去${OFF}"; exit 1; }
codesign --verify "$APP" >/dev/null 2>&1 \
    || { echo "${RED}✗ 签名验不过${OFF}"; exit 1; }
echo "  ${GREEN}✓${OFF} 签名有效"

echo
echo "${BOLD}[4/4] 六项检查${OFF}"
for TARGET in swift/Sources/MechanicsOneApp swift/Sources/MechanicsKit; do
    bash tools/ci/check_binary_hygiene.sh "$TARGET" >/dev/null 2>&1 \
        || { echo "  ${RED}✗ S-1..3 在 $TARGET 上未通过${OFF}"; FAILED=1; }
done
[ "$FAILED" -eq 0 ] && echo "  ${GREEN}✓${OFF} S-1 S-2 S-3（源码：App 层与 kernel）"

bash tools/ci/check_binary_hygiene.sh "$APP" >/dev/null 2>&1 \
    && echo "  ${GREEN}✓${OFF} S-4 S-5 S-6（成品包）" \
    || { echo "  ${RED}✗ S-4..6 在成品包上未通过${OFF}"; FAILED=1; }

bash tools/ci/check_plists.sh swift/App "$APP" >/dev/null 2>&1 \
    && echo "  ${GREEN}✓${OFF} plist 纪律（规范化 + 严格解析）" \
    || { echo "  ${RED}✗ plist 未通过${OFF}"; FAILED=1; }

echo
if [ "$FAILED" -eq 0 ]; then
    echo "${GREEN}${BOLD}Gate S 六项全数通过。${OFF}"
    echo "  包：$APP"
    echo
    echo "  仍未验的：内嵌描述文件的 application-identifier（90886）——"
    echo "  那需要真正的 App Store 描述文件，在阶段 08。"
    exit 0
fi
echo "${RED}${BOLD}Gate S 未通过。${OFF}"
echo "在这些修掉之前不要投递 —— 它们的代价是账号，不是一次重新提交。"
exit 1

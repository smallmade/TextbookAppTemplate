#!/bin/bash
# Gate 08 —— plist 纪律：凡进包的 plist 一律先规范化再严格解析。
#
#   bash check_plists.sh <目录或 .app>
#
# 贯穿性教训：**本地宽容检查是骗人的。**
#   plutil -lint 放行的 plist（XML 注释里的一对连字符），Apple 服务端严格
#   解析直接拒收（ITMS-91056）。同类问题也杀过 entitlements（AMFI syntax
#   error）——手签直通 AMFI 会死。
set -uo pipefail
T="${1:-}"; [ -e "$T" ] || { echo "用法: bash check_plists.sh <目录或 .app>" >&2; exit 2; }
RED=$'\033[31m'; GREEN=$'\033[32m'; BOLD=$'\033[1m'; OFF=$'\033[0m'
FAIL=0

echo; echo "${BOLD}Gate 08 · plist 纪律${OFF}"
while IFS= read -r p; do
    name="${p#$T/}"
    # 1) plutil -lint：宽容层，过不了这关肯定不行
    if ! plutil -lint "$p" >/dev/null 2>&1; then
        echo "  ${RED}✗${OFF} $name —— plutil -lint 都过不了"; FAIL=$((FAIL+1)); continue
    fi
    # 2) 严格解析：XML 注释里的 -- 是非良构，而 plutil -lint 会放行
    #
    # 二进制 plist 先转成 XML 再解析，不是直接放行。iOS 的 app bundle 里
    # Xcode 出的就是二进制格式，强行要求 XML 等于让这道闸门逼人偏离平台
    # 常规——而一个逼人写不地道东西的闸门会被关掉。转一遍既保住了严格解析，
    # 也顺带证明这份二进制 plist 本身是良构的：转不出来就是坏的。
    if ! python3 -c "
import subprocess, sys, xml.dom.minidom
path = sys.argv[1]
with open(path, 'rb') as fh:
    head = fh.read(8)
if head.startswith(b'bplist'):
    out = subprocess.run(['plutil', '-convert', 'xml1', '-o', '-', path],
                         capture_output=True)
    if out.returncode != 0:
        raise SystemExit(1)
    xml.dom.minidom.parseString(out.stdout)
else:
    xml.dom.minidom.parse(path)" "$p" >/dev/null 2>&1; then
        echo "  ${RED}✗${OFF} $name —— 严格 XML 解析失败（多半是注释里的双连字符）"
        echo "        修法：plutil -convert xml1 覆写它，注释会被剥掉"
        FAIL=$((FAIL+1)); continue
    fi
    echo "  ${GREEN}✓${OFF} $name"
done < <(find "$T" \( -name "*.plist" -o -name "*.xcprivacy" -o -name "*.entitlements" \) -type f 2>/dev/null)

echo
[ "$FAIL" -eq 0 ] && { echo "${GREEN}${BOLD}plist 纪律通过。${OFF}"; echo; exit 0; }
echo "${RED}${BOLD}未通过：$FAIL 项。${OFF}"; echo; exit 1

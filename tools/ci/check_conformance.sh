#!/bin/bash
# Gate 05 · 跨语言 conformance：Swift 侧跑同一份高精度 fixture。
#
#   bash check_conformance.sh <项目目录>
#
# 对等测试（check_port_coverage.py）只比名字。这一道比数：两种语言读**同一个
# 文件**，调用同一批关系式，和同一批六十位参考值比对。
#
# 层 2 而不是层 1，理由在规范里：四位印刷数字分不出「正确的翻译」和「有细微
# 失误的翻译」——一个 pow 对错、一个减法次序颠倒，会在第十二位显现，远早于
# 第四位。
#
# 顺带核对正典指纹：两侧对**同一批字节**各算一次 FNV-1a，相等才算「读的是
# 同一份正典」。文件名相同不算。
#
# 退出码：0 通过 · 1 未通过 · 2 尚不适用（跳过）。
set -uo pipefail
P="$(cd "${1:-.}" && pwd)"
RED=$'\033[31m'; GREEN=$'\033[32m'; OFF=$'\033[0m'

[ -f "$P/swift/Package.swift" ] || { echo "尚不适用：还没有 swift/Package.swift —— 阶段 05 之前正常"; exit 2; }
command -v swift >/dev/null 2>&1 || { echo "尚不适用：这台机器上没有 swift"; exit 2; }

out="$(cd "$P/swift" && swift run -c release StructureKitVerify 2>&1)"
code=$?
echo "$out" | grep -vE '^\[|^Building|^Compiling|^Fetching|^Build (of|complete)'
if [ $code -ne 0 ]; then
    echo "${RED}✗ conformance 未通过${OFF}"
    exit 1
fi

# 指纹比对：Python 侧对同一批字节重算一次。
swift_print="$(echo "$out" | grep -oE 'fingerprint [0-9a-f]{16}' | awk '{print $2}')"
python_print="$(python3 - "$P/spec/specification.json" <<'PY'
import sys, pathlib
data = pathlib.Path(sys.argv[1]).read_bytes()
value = 0xCBF29CE484222325
for byte in data:
    value ^= byte
    value = (value * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
print(f"{value:016x}")
PY
)"
if [ -z "$swift_print" ]; then
    echo "${RED}✗ Swift 侧没有报告正典指纹${OFF}"
    exit 1
fi
if [ "$swift_print" != "$python_print" ]; then
    echo "${RED}✗ 正典指纹不一致：swift $swift_print · python $python_print${OFF}"
    echo "  两侧读的不是同一份正典。多半是 swift 的 Fixtures 副本过期了。"
    exit 1
fi
echo "${GREEN}✓ 正典指纹一致：$swift_print${OFF}"
exit 0

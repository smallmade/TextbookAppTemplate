#!/bin/bash
# 本项目的全闸门。任何一项失败即整体失败。
#
#   bash tools/ci/run_gates.sh
#
# 顺序有意义：正典先于代码，架构不变量先于测试。阶段 05 之后的闸门（Swift
# 对等、conformance、二进制卫生）在 swift/ 存在之前会被跳过并明确标注为
# 【尚未到达】——不是通过。一道报告「零命中 ✓」而其实没有运行的闸门，比没有
# 闸门更糟。
set -uo pipefail
cd "$(dirname "$0")/../.."
export PYTHONPATH="src:engkit/python${PYTHONPATH:+:$PYTHONPATH}"

PASS=0; FAIL=0; SKIP=0
step() { echo; echo "── $1 ──"; shift
    if "$@"; then echo "  ✓"; PASS=$((PASS+1)); else echo "  ✗ 未通过"; FAIL=$((FAIL+1)); fi; }
pending() { echo; echo "── $1 ──"; echo "  ⋯ 尚未到达（阶段 $2）"; SKIP=$((SKIP+1)); }

mkdir -p build

step "Gate 01 · 开发正典" \
     python3 tools/ci/check_spec.py spec/specification.json
step "Gate 01 · 剥离出货副本" \
     python3 tools/ci/strip_spec.py spec/specification.json build/specification.shipped.json
step "Gate 01 · 出货副本复检" \
     python3 tools/ci/check_spec.py --shipped build/specification.shipped.json
step "闸门自检（必须能抓到已知不合格样本）" \
     python3 tools/ci/check_spec.py --selftest spec/specification.json
step "Gate 01+ · 正典 function 指针可解析" \
     python3 tools/ci/check_canon_functions.py spec/specification.json --python src
step "架构不变量 1+2 · kernel 零依赖" \
     bash tools/ci/check_kernel_purity.sh src/thermo
step "架构不变量 3 · 生成表与正典无漂移" \
     python3 tools/build/codegen_data.py --check
step "全部测试" \
     python3 -m pytest -q --no-header -x
step "Gate 02 · 五层验证充分性" \
     python3 tools/ci/check_sufficiency.py

pending "Gate 05 · 对等测试 / 跨语言 conformance" "05 Apple 移植"
pending "Gate 06 · 法律隔离 · 成品面"            "06 界面"
pending "Gate S · 出货二进制卫生"                 "S 出货二进制"
pending "Gate 07 · 文案字数 / 截图尺寸 / URL"     "07 手册与站点"

echo
echo "════════════════════════════════════════════"
printf "通过 %d · 未通过 %d · 尚未到达 %d\n" "$PASS" "$FAIL" "$SKIP"
[ "$FAIL" -eq 0 ] || echo "闸门不通过就不进下一阶段。"
exit $(( FAIL > 0 ))

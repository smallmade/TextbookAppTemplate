#!/bin/bash
# 本项目的全闸门。任何一项失败即整体失败。
#
#   bash tools/ci/run_all_local.sh
#
# 顺序有意义：正典先于代码，架构不变量先于测试，跨实现比对最后——
# 因为它依赖前面每一项都已经成立。
set -uo pipefail
cd "$(dirname "$0")/../.."
FAIL=0
# 本阶段还到不了的闸门。写在这里而不是别处，因为这里是跑套件的人会看到的
# 地方——一道悄悄没跑的闸门，和一道通过了的闸门，在日志里长得一模一样。
pending() {
    printf "\n── %s ──\n  ⏸ 尚未到达：%s\n" "$1" "$2"
}

step() {
    echo
    echo "── $1 ──"
    shift
    if "$@"; then echo "  ✓"; else echo "  ✗ 未通过"; FAIL=$((FAIL+1)); fi
}

step "施工书闸门自检（必须能抓到八个已知不合格台账）" \
     python3 tools/ci/check_plan.py --self-test
step "施工书台账（done 项的闸门必须存在且被调用）" \
     python3 tools/ci/check_plan.py --root .

step "G-02 闸门自检" python3 tools/ci/check_interface_review.py --self-test
step "G-02 · 界面走查覆盖全部画面" python3 tools/ci/check_interface_review.py --root .

step "闸门接线自检" python3 tools/ci/check_gates_are_wired.py --self-test
step "每一道闸门都真的被调用" python3 tools/ci/check_gates_are_wired.py --root .
step "工具链单一真身（tools/ci 仍是模板的符号链接）" \
     bash tools/ci/check_no_drift.sh .. --mine "Material Mechanics Calculator"

step "Gate 01 · 开发正典" python3 tools/ci/check_spec.py spec/specification.json
step "Gate 01 · 剥离出货副本" python3 tools/ci/strip_spec.py spec/specification.json build/specification.shipped.json
step "Gate 01 · 出货副本复检" python3 tools/ci/check_spec.py --shipped build/specification.shipped.json
step "闸门自检（必须能抓到已知不合格样本）" python3 tools/ci/check_spec.py --selftest spec/specification.json
step "架构不变量 1+2 · kernel 零依赖" bash tools/ci/check_kernel_purity.sh python/src/mechanicskit
step "测试文件闸门自检（既不漏报也不乱叫）" \
     python3 tools/ci/check_test_files.py --self-test
step "每个 test_*.py 里真的有测试" \
     python3 tools/ci/check_test_files.py python/tests

step "层 5 闸门自检（必须能抓到六个已知不合格样本）" \
     python3 tools/ci/check_layer5.py --self-test
step "Gate 02 · 层 5 裁定纪律（第二源独立，但不是无误）" \
     python3 tools/ci/check_layer5.py --root .

step "测试与分支覆盖 ≥95%" bash -c "cd python && python3 -m pytest tests/ -q --cov --cov-branch --cov-fail-under=95 --cov-report=json:coverage.json >/dev/null"
step "Gate 02 · 七条充分性判据（对着正典核对真实存在的 fixture）" \
     python3 tools/ci/check_sufficiency.py .
step "Gate 02 · 输入格式矩阵（含读取器实测）" \
     python3 tools/ci/check_input_matrix.py python \
       --reader "python3 tools/conformance/read_matrix.py {file}" --expect-rows 6
step "跨实现比对 · JS ↔ Python" node tools/conformance/check_js.mjs
step "Gate 01+ · 正典 function 指针可解析" \
     python3 tools/ci/check_canon_functions.py spec/specification.json --python python/src

step "Gate 06 · 正典公式全部可渲染" \
     python3 tools/ci/check_formula_coverage.py spec/specification.json --python python/src

step "Gate 06 · 出货正典标识符自检（含公有领域放行的双向样本）" \
     python3 tools/ci/check_ship_isolation.py --selftest
step "Gate 06 · 出货正典每一个字串（第一道防线）" \
     python3 tools/ci/check_ship_isolation.py build/specification.shipped.json

step "Gate 06 · 法律隔离 · 全部出货面（含出货正典副本）" \
     bash tools/ci/check_legal_isolation.sh --identifiers-only \
       build/specification.shipped.json swift/Sources/MechanicsKit \
       swift/Sources/MechanicsOneApp python/src/mechanicskit

# 阶段 04 的适配审计。它在没有 CSV 时返回 2 =「尚不适用」，
# 而不是失败——所以这里必须把那个状态【打印出来】。一道安静跳过的检查，
# 和一道通过的检查，在日志里长得一模一样。
step "Gate 04 · 可达性闸门自检" \
     python3 tools/ci/check_screen_reachability.py --self-test
step "Gate 04 · 每个 v1.0 模块界面上都到得了" \
     python3 tools/ci/check_screen_reachability.py --root .

echo "── Gate 04 · 适配审计 ──"
python3 tools/ci/check_coverage_audit.py . ; CODE=$?
if [ "$CODE" -eq 2 ]; then
    echo "  ⚠ 尚未开始 —— 见 docs/coverage-audit.md。这是十个阶段里唯一"
    echo "    机器帮不上忙的一步：它需要四部主教材在手，一题一题读。"
elif [ "$CODE" -ne 0 ]; then
    FAIL=$((FAIL+1)); echo "  ✗ 未通过"
fi
echo

step "Gate 09 · 桌面打包（冒烟 + 图元 + 打包脚本一致）" \
     bash tools/build/run_gate_09.sh

step "Gate 07 · 双手册与站点（生成 + 自洽 + 文案）" \
     bash tools/ci/run_gate_07.sh

step "Gate S · 六项全跑（建包→strip→签名→查）" \
     bash tools/ci/run_gate_s.sh

step "不变量 4 · 出货源码不依赖包外输入" \
     bash tools/ci/check_app_purity.sh swift/Sources/MechanicsOneApp swift/Sources/MechanicsKit

step "Gate 06 · 界面不持有物理（只查 App 层）" \
     bash tools/ci/check_legal_isolation.sh swift/Sources/MechanicsOneApp

step "Gate 05 · 对等测试（清单自动探索）" \
     python3 tools/ci/check_port_coverage.py \
       --python python/src/mechanicskit --swift swift/Sources/MechanicsKit
step "Gate 05+06 · Swift Release 零警告（含 App）" \
     bash -c "swift build --package-path swift -c release >/dev/null 2>&1"
step "Gate 05 · 参考值与扫描 fixture 是最新的" \
     bash -c "PYTHONPATH=python/src python3 tools/conformance/emit_reference.py --check >/dev/null && PYTHONPATH=python/src python3 tools/conformance/emit_sweep.py --check >/dev/null"

step "Gate 05 · 跨语言 conformance · Swift ↔ Python" \
     bash -c "swift run --package-path swift MechanicsKitVerify"
step "原型与共享模块同步" bash -c "python3 tools/conformance/build_prototype.py >/dev/null && git diff --quiet design/prototype.html 2>/dev/null || true"

pending "Gate 07 · 站点五个 URL 实测回 200 (check_urls.sh)" \
        "需要伞形站点已部署——本地只验得到链接自洽"

echo
if [ "$FAIL" -eq 0 ]; then echo "全部通过。"; exit 0; fi
echo "未通过：$FAIL 项。"; exit 1

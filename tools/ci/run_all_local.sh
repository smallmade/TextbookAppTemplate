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

# [M-03] 三态版的 step。
#
# `step` 只有两态，于是任何一道「本阶段尚不适用」的闸门在这里都是红的，
# 而把它写成 `pending` 又等于永远不跑它。三态版按 run_all.sh 的同一套约定
# 判：0 通过 / 1 未通过 / 2 尚不适用（**必须说出理由**）。
#
# 退出码 2 要过两道关，理由与 run_all.sh 里一字不差：argparse 的参数用法
# 错误也是 exit 2，而它不是「本阶段不适用」。
gate() {
    echo
    echo "── $1 ──"
    shift
    local out code n
    out="$("$@" 2>&1)"; code=$?
    n="$(echo "$out" | sed -nE 's/.*CHECKED n=([0-9]+).*/\1/p' | tail -1)"
    echo "$out" | sed 's/^/  /'
    case $code in
        0) if [ "${n:-1}" = "0" ]; then
               echo "  ✗ 未通过：报了通过，却一个对象都没检查"
               FAIL=$((FAIL+1))
           else
               echo "  ✓${n:+  （$n 个对象）}"
           fi ;;
        2) if echo "$out" | grep -qE '(^|[^A-Za-z])(usage:|error:)|the following arguments are required'; then
               echo "  ✗ 未通过：退出码 2 来自参数用法错误，不是「不适用」"
               FAIL=$((FAIL+1))
           elif echo "$out" | grep -qE '(尚)?不适用'; then
               echo "  ⏸ 尚不适用（理由见上）"
           else
               echo "  ✗ 未通过：退出 2 却没有说「尚不适用」以及为什么"
               FAIL=$((FAIL+1))
           fi ;;
        *) echo "  ✗ 未通过"; FAIL=$((FAIL+1)) ;;
    esac
}

# ══════════════════════════════════════════════════════════════
# 项目形状：读 <项目根>/ci.toml，读不到就自动探测。
#
# 这个 runner 是【多款 App 共用的同一个文件】——tools/ci 是指向模板仓库的
# 符号链接。它却把某一款 App 的目录形状写死在命令行上：python/src/mechanicskit、
# swift/Sources/MechanicsOneApp、swift/App/MechanicsOne.entitlements、
# --slug mechanicsone、python/tests……于是别的项目要用它，只能再抄一份。
#
# 抄一份的代价这份文件自己就记着——见上面 --mine 那一段：写死的项目名让
# 姊妹项目报的是别人那一格，**不会红，只会答错**。而写死的【路径】更糟：
# 闸门按别人的形状找不到东西，自己印一句「尚不适用」退 2，于是被印成一行
# 黄色的跳过。一道按别人的目录形状宣布自己不适用的闸门，与一道通过了的
# 闸门，在日志里长得一模一样。
#
# run_all.sh 与 run_gates.sh 已经先后走通这条路，这是最后一个还写死形状的
# runner。形状由项目自己在 ci.toml 里声明，脚本读它。
# ══════════════════════════════════════════════════════════════
eval "$(python3 tools/ci/ci_config.py --root . --shell)"
CI_CANON="${CI_CANON:-}"
CI_SHIPPED_CANON="${CI_SHIPPED_CANON:-build/specification.shipped.json}"
CI_PYTHON_PACKAGE_DIR="${CI_PYTHON_PACKAGE_DIR:-}"
CI_PYTHON_SRC_DIR="${CI_PYTHON_SRC_DIR:-}"
CI_TESTS_DIR="${CI_TESTS_DIR:-}"
CI_SWIFT_APP_DIR="${CI_SWIFT_APP_DIR:-}"
CI_SWIFT_KIT_DIR="${CI_SWIFT_KIT_DIR:-}"
CI_ENTITLEMENTS="${CI_ENTITLEMENTS:-}"
CI_SITE_DIR="${CI_SITE_DIR:-site}"
CI_SLUG="${CI_SLUG:-}"

# pytest 与输入矩阵是按【目录】跑的，而 ci.toml 只声明 tests_dir 一个键。
# PYDIR 是它的父目录：pyproject.toml 的 [tool.pytest.ini_options] 与
# [tool.coverage.run] 在那里，所以那几步必须先 cd 进去，不能改成从仓库根
# 指着测试目录跑——那会换掉 pytest 的 rootdir，连带换掉覆盖率的配置来源。
# TESTS 是测试目录相对 PYDIR 的名字。
#   tests_dir="python/tests" → PYDIR="python"  TESTS="tests"
#   tests_dir="tests"        → PYDIR="."       TESTS="tests"
PYDIR="$(dirname "${CI_TESTS_DIR:-.}")"
TESTS="$(basename "${CI_TESTS_DIR:-tests}")"

# 一个值没声明、或它指的东西根本不在 —— 这不是跳过。
# 「没有东西可查」与「查过了是干净的」必须分得开（架构不变量 6）。
missing() {
    printf "\n── %s ──\n  ✗ 未通过 —— %s\n" "$1" "$2"
    FAIL=$((FAIL+1))
}

# need <名称> <ci.toml 的键…> -- <命令…>
#
# 键全都有值、且指的路径存在 → 照常交给 step；任一缺席 → missing（未通过）。
# 报的是【键名】而不是路径，因为看日志的人接下来要做的事，是去 ci.toml 补
# 那一行。键只收路径类的：slug 不是路径，它在下面单独判。
#
# 两处刻意的写法：
#   · 不用数组。这台机器上 /bin/bash 是 3.2，空数组的 ${#a[@]} 在 set -u 下
#     报 unbound variable，而这类差异只在别人的机器上现形——本仓库已经为
#     「本机重现不了」的 shell 差异付过一次学费（$VERSION 紧跟全形逗号）。
#   · 少写 `--` 时【大声失败】。漏了它的话 "$@" 会是空的，而 `if "$@"` 对空
#     参数返回 0——一道什么都没跑的闸门报 ✓，正是这个文件通篇在防的事。
need() {
    local name="$1"; shift
    local key var val gone="" saw=""
    while [ $# -gt 0 ]; do
        if [ "$1" = "--" ]; then saw=yes; shift; break; fi
        key="$1"; shift
        var="CI_$(echo "$key" | tr '[:lower:]' '[:upper:]')"
        val="${!var:-}"
        if [ -z "$val" ] || [ ! -e "$val" ]; then gone="$gone $key"; fi
    done
    if [ -z "$saw" ] || [ $# -eq 0 ]; then
        missing "$name" "need 用法错：少了 -- 或它后面的命令（脚本自己的错，不是项目的）"
    elif [ -n "$gone" ]; then
        missing "$name" "ci.toml 缺这些键，或它们指的路径不在：${gone# }"
    else
        step "$name" "$@"
    fi
}

step "施工书闸门自检（必须能抓到八个已知不合格台账）" \
     python3 tools/ci/check_plan.py --self-test
step "施工书台账（done 项的闸门必须存在且被调用）" \
     python3 tools/ci/check_plan.py --root .

step "G-02 闸门自检" python3 tools/ci/check_interface_review.py --self-test
step "G-02 · 界面走查覆盖全部画面" python3 tools/ci/check_interface_review.py --root .

step "闸门接线自检" python3 tools/ci/check_gates_are_wired.py --self-test
step "每一道闸门都真的被调用" python3 tools/ci/check_gates_are_wired.py --root .
# `--mine` 指出哪一格是【本项目】的：只有自己那一格算失败，别人的算情报。
# 这里曾经写死 "Material Mechanics Calculator"，而本脚本是共用的：热力学那一款
# 跑起来时，报的是 MechanicsOne 那一格的状态，自己那一格根本没查。它不会红，
# 只会**答错**——这比红灯更难发现。项目名由脚本开头 `cd` 到的目录自己说。
step "工具链单一真身（tools/ci 仍是模板的符号链接）" \
     bash tools/ci/check_no_drift.sh .. --mine "$(basename "$PWD")"

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
     python3 tools/ci/check_layer5.py --root . --min-layer5-modules 18

step "第二源声明闸门自检（必须能抓到已知不合格样本）" \
     python3 tools/ci/check_second_source.py --self-test
step "Gate 02 · 正典的 second_source 声明与层 5 实建 fixture 对得上" \
     python3 tools/ci/check_second_source.py --root .

step "层 3 闸门自检（必须能抓到两个已知不合格样本）" \
     python3 tools/ci/check_layer3_symbolic.py --self-test
step "Gate 02 · 层 3 符号证明真的被执行" \
     python3 tools/ci/check_layer3_symbolic.py --root .

step "测试与分支覆盖 ≥95%" bash -c "cd python && python3 -m pytest tests/ -q --cov --cov-branch --cov-fail-under=95 --cov-report=json:coverage.json >/dev/null"

# [B-18] M17-I4 的两条独立算法互证，单独点名一步。
# 它本来就在上面那个 pytest 里跑，之所以还要单列：这个文件是全 App 单点故障
# （组合截面）唯一的独立证据，而它曾经【整个文件里 rotation 出现零次】——
# 一段只在部件旋转时才跑的代数，两种语言里符号都反了，Ix 与 Iy 差 52%，
# 而上面那个 pytest 只会报一个总数，没有人会注意到它少测了什么。
# 名字出现在日志里，是为了它哪天不再运行时有人看得见。
step "M17-I4 · 闭式求和 vs 边界积分（含旋转）" \
     bash -c "cd python && python3 -m pytest tests/test_outline.py -q >/dev/null"

# [E-09] 屏上印出来的校核，本身能不能失败。
# 单列的理由和上面那步一样：E-09 走查发现塑性屏印的「净力为零」对任何反对称
# 分布恒成立，而开屏默认弯矩超过该截面塑性弯矩、被当成一致的往返展示。
# 两处都不是数值误差，是【印错了量并当作证据】——上面那个 pytest 只报总数。
step "屏上校核本身能不能失败（开屏状态 · 残余平衡 · 决策不印量纲）" \
     bash -c "cd python && python3 -m pytest tests/test_plastic_residual_equilibrium.py tests/test_latex.py -q >/dev/null"
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

# [E-02] v1.1 那一档更严：在这一档里 partial 也失败，界面「做了一半」的模块
# 必须要么补上入口，要么在正典里写明 ui_deferred 与理由。
step "Gate 04 · v1.1 那一档（partial 也算失败）" \
     python3 tools/ci/check_screen_reachability.py --root . --release v1.1

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

# [M-A19] 这一步以前直接跑 MechanicsKitVerify，而把 check_conformance.sh
# 挂在末尾的 pending 里，理由写的是「直接跑比包装脚本更严」。对 7980 个值
# 那句话成立，对**正典指纹**不成立：直接跑那一步比的是 Swift 读到的活文件
# 与 reference.json 里记下的 sha256，要再借 emit_reference.py --check 那一步
# 接力才等价于「两侧此刻读的是同一批字节」。包装脚本自己就把两侧的活值各算
# 一次当场比——而它那一步从写下来那天起就只会走到「Swift 侧没有报告正典
# 指纹」，因为 main.swift 里压根没印过那行。印上了，于是这里改成跑包装脚本
# 本身：**被文档写成闸门的那一个，就该是真的在跑的那一个。**
gate "Gate 05 · 跨语言 conformance · Swift ↔ Python（含正典指纹）" \
     bash tools/ci/check_conformance.sh .
step "原型与共享模块同步" bash -c "python3 tools/conformance/build_prototype.py >/dev/null && git diff --quiet design/prototype.html 2>/dev/null || true"

# [2026-09-01] check_site.py 曾经在没给 --slug 时默认落到另一个姊妹项目的
# slug（"structuremechone"）——本地全绿，末尾印出的五个 URL 却指向别人的站点。
# 现在该参数必须显式给，这里补上，让这一半（部署前能查的一半）真的进套件，
# 不再只是一个手动才会想起来跑的命令。
# [A-20] entitlements 声明的能力，代码里没有对应 API——找到时它是
# com.apple.security.files.user-selected.read-write（为已推迟到 v2 的导出
# 功能预留，A-11 推迟决定之后没人回头把这把键摘掉）。自检里带了一个已知
# 会失败的样本，就是那把键当时的样子。
step "entitlements 里的能力声明，代码里都有对应 API 在用" \
     python3 tools/ci/check_entitlements.py --self-test
step "  同上，对真身跑一次" \
     python3 tools/ci/check_entitlements.py \
       swift/App/MechanicsOne.entitlements swift/Sources/MechanicsOneApp

step "Gate 07 · 站点自洽（页面齐备 / 链接 / 隐私页与隐私清单一致）" \
     python3 tools/ci/check_site.py site/ --slug mechanicsone
pending "Gate 07 · 站点五个 URL 实测回 200 (check_urls.sh)" \
        "需要伞形站点已部署——本地只验得到链接自洽"

# ══════════════════════════════════════════════════════════════
# [M-03] 本轮新增的九道闸门，以及三道原本没被本项目 runner 调用的。
#
# 全部走 gate()（三态），因为其中好几道现在就该是「尚不适用」——设备矩阵
# 还没开始、探针生成器还没写。把它们写成 pending 等于永远不跑；写成 step
# 又会把一个诚实的「尚未开始」印成红灯。三态是唯一诚实的记法。
# ══════════════════════════════════════════════════════════════
gate "自检 · 分支可见" python3 tools/ci/check_branching_visible.py --self-test
gate "Gate M1 · 每条 branching 都有可见控件" \
     python3 tools/ci/check_branching_visible.py --root .

gate "自检 · 界面字串" python3 tools/ci/check_ui_strings.py --self-test
gate "Gate 06A · 会上屏的字面量零占位符" \
     python3 tools/ci/check_ui_strings.py --root .

gate "自检 · 原生对标" python3 tools/ci/check_native_parity.py --self-test
gate "Gate 06A · 菜单 / 帮助 / 关于 / 设置 / 导出都有落点" \
     python3 tools/ci/check_native_parity.py --root .

gate "自检 · 手册进包" python3 tools/ci/check_help_bundled.py --self-test
gate "Gate 07 · 两册手册在包里且 App 打得开" \
     python3 tools/ci/check_help_bundled.py --root .

gate "自检 · 手册覆盖" python3 tools/ci/check_manual_coverage.py --self-test
gate "Gate 07 · 理论手册每模块一节 / 使用手册每画面一节" \
     python3 tools/ci/check_manual_coverage.py --root .

gate "自检 · 理论手册散文源" python3 tools/ci/check_theory.py --self-test
gate "Gate 07 · 理论手册散文源完整、有实质、且经对抗复核" \
     python3 tools/ci/check_theory.py --root .

gate "自检 · 手册与站点零标识" python3 tools/ci/check_manual_isolation.py --self-test
gate "Gate 07 · 两册与站点全文零教材标识" \
     python3 tools/ci/check_manual_isolation.py --root .

gate "自检 · 设备矩阵" python3 tools/ci/check_device_matrix.py --self-test
gate "Gate 06B · 设备矩阵每格每屏截图齐全" \
     python3 tools/ci/check_device_matrix.py --root .

gate "自检 · 未覆盖分支说明" python3 tools/ci/check_coverage_gaps.py --self-test
gate "Gate 03 · coverage-gaps.md 与实测逐条一致" \
     python3 tools/ci/check_coverage_gaps.py --root .

gate "自检 · App 图标" python3 tools/ci/check_icon.py --self-test
gate "Gate M7 · 图标十档齐全且真在成品包里" \
     python3 tools/ci/check_icon.py --root .

# 这三道存在已久，而本项目的 runner 从没调用过它们——元闸门在旧判据下
# 因为【姊妹项目的】runner 提到过它们而放行。
gate "Gate 02 · 引用页码核对" python3 tools/ci/check_citations.py --root .
gate "Gate 06 · 画面图形覆盖" python3 tools/ci/check_figures.py --root .
gate "Gate 08 · 构建号台账" python3 tools/ci/check_ledger.py .
gate "Gate 07 · 截图尺寸" python3 tools/ci/check_screenshots.py submission/screenshots
echo
if [ "$FAIL" -eq 0 ]; then echo "全部通过。"; exit 0; fi
echo "未通过：$FAIL 项。"; exit 1

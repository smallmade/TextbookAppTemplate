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
# 摸不到要查的东西 = 【未通过】，不是「干净」。
missing() { echo; echo "── $1 ──"; echo "  ✗ 未通过 —— $2"; FAIL=$((FAIL+1)); }
# 这一项对本 App 不适用，而且【说明理由】。安静跳过与通过必须分得开。
na()      { echo; echo "── $1 ──"; echo "  ⋯ 尚不适用 —— $2"; SKIP=$((SKIP+1)); }

# ── 项目形状：一律走 ci.toml，不写死任何一款 App 的目录 ────────────────────
#
# 这个 runner 是【多款 App 共用的同一个文件】——tools/ci 指向模板仓库的
# checkout。它却把 `src/thermo` 直接写在命令行上，那是热力学那一款的包目录。
# 于是在另外几款上，check_kernel_purity.sh 收到一个不存在的路径、印出用法、
# 以退出码 2 结束，runner 把它记成「✗ 未通过」。
#
# 【未通过】与【根本没查】在日志里长得一模一样，而真相是后者：零依赖纪律
# 在那几款 App 上从来没有被检查过。把 src/thermo 改成另一款的包目录只是把
# 这个洞轮换给别人——所以路径必须参数化。
#
# ci_config.py 读 <项目根>/ci.toml；没有 ci.toml 时它自动探测目录形状（实测
# 在热力学那一款上探测出来的正是 src/thermo），所以这条路对每一款都成立。
eval "$(python3 tools/ci/ci_config.py --root . --shell 2>/dev/null || true)"
CI_PYTHON_PACKAGE_DIR="${CI_PYTHON_PACKAGE_DIR:-}"
CI_PYTHON_SRC_DIR="${CI_PYTHON_SRC_DIR:-}"

mkdir -p build

step "Gate 01 · 开发正典" \
     python3 tools/ci/check_spec.py spec/specification.json
step "Gate 01 · 剥离出货副本" \
     python3 tools/ci/strip_spec.py spec/specification.json build/specification.shipped.json
step "Gate 01 · 出货副本复检" \
     python3 tools/ci/check_spec.py --shipped build/specification.shipped.json
step "闸门自检（必须能抓到已知不合格样本）" \
     python3 tools/ci/check_spec.py --selftest spec/specification.json
# 同一类写死：`--python src` 在包树位于 python/src 的那一款上指向一个不存在
# 的目录，check_canon_functions.py 于是印「尚不适用：找不到 Python 源目录 src」
# 并以退出码 2 结束，runner 记成「✗ 未通过」。它的报错原文就写着解法：
# ci.toml 的 python_src_dir 可以点名它。
if [ -n "$CI_PYTHON_SRC_DIR" ] && [ -d "$CI_PYTHON_SRC_DIR" ]; then
    step "Gate 01+ · 正典 function 指针可解析" \
         python3 tools/ci/check_canon_functions.py spec/specification.json \
                 --python "$CI_PYTHON_SRC_DIR"
else
    missing "Gate 01+ · 正典 function 指针可解析" \
            "摸不到 Python 源目录 —— 在 ci.toml 里写 python_src_dir"
fi
if [ -n "$CI_PYTHON_PACKAGE_DIR" ] && [ -d "$CI_PYTHON_PACKAGE_DIR" ]; then
    step "架构不变量 1+2 · kernel 零依赖" \
         bash tools/ci/check_kernel_purity.sh "$CI_PYTHON_PACKAGE_DIR"
elif [ -d src ] || [ -d python ]; then
    missing "架构不变量 1+2 · kernel 零依赖" \
            "有 Python 树却摸不到包目录 —— 在 ci.toml 里写 python_package_dir"
else
    pending "架构不变量 1+2 · kernel 零依赖" "03 核心实现"
fi
# codegen_data.py 同样是「按一款 App 写死」：只有带生成数据表的那一款有它。
if [ -f tools/build/codegen_data.py ]; then
    step "架构不变量 3 · 生成表与正典无漂移" \
         python3 tools/build/codegen_data.py --check
else
    na "架构不变量 3 · 生成表与正典无漂移" \
       "本 App 没有 tools/build/codegen_data.py（没有由正典生成的数据表）"
fi
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

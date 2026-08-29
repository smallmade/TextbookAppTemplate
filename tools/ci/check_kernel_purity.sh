#!/bin/bash
# 架构不变量 1 与 2 —— kernel 零运行期依赖；四层不含平台代码。
#
#   bash check_kernel_purity.sh <src/包目录>
#
# 零依赖不是风格偏好：零依赖的东西才能同时活在 Python、Swift 甚至 C++ 里，
# 而整个跨平台架构就建立在这一条上面。违反它，跨平台立刻失效，而且要到
# 移植时（阶段 05）才会发现。
set -uo pipefail
PKG="${1:-}"
[ -d "$PKG" ] || { echo "用法: bash check_kernel_purity.sh <src/包目录>" >&2; exit 2; }

RED=$'\033[31m'; GREEN=$'\033[32m'; BOLD=$'\033[1m'; OFF=$'\033[0m'
FAIL=0

# 只匹配真正的 import 语句，不匹配散落的词。
#
# 第一版写的是裸词匹配，结果把 ui/__init__.py 文档字串里那句「这一层不
# import 任何 GUI 库」当成了违规——解释规则的那句话被判成违反规则。一个会
# 这样乱叫的闸门，两天之内就会被关掉。
#
# 版本号要写进模式：PySide 与 6 之间没有词边界，(PySide|...)\b 匹配不上
# `from PySide6 import QtCore`。这一条是被自己咬过才发现的——见下面的双向自检。
# `from` 后面必须跟一个合法模块名，`from X` 后面必须跟 ` import `。
# 少了这一条，docstring 里一句折行后以 from 开头的散文就会被判成 import——
# StructureOne 的 kernel 上真的发生过，那一行是：
#     from :func:`principal_angle` is meaningless rather than merely imprecise.
# 这是第二次栽在「行级 grep 看不见 docstring」上，第一次是 ui 层那句
# 「这一层不 import 任何 GUI 库」。行级检查看不到语法，只能把模式收紧到
# 语法本身：from 之后必须是模块名，且必须跟一个 import。
MODNAME='[A-Za-z_][A-Za-z0-9_.]*'
IMPORT="^[[:space:]]*(import[[:space:]]+${MODNAME}|from[[:space:]]+[.]*${MODNAME}[[:space:]]+import[[:space:]])"
LIBS='(PySide[0-9]*|PyQt[0-9]*|SwiftUI|UIKit|AppKit|tkinter)'
IMPORT_HEAD='^[[:space:]]*(import|from)[[:space:]]+'
PLATFORM="${IMPORT_HEAD}(${LIBS}|pathlib|subprocess|requests|urllib|os)([.,[:space:]]|$)"
UI_PATTERN="${IMPORT_HEAD}${LIBS}([.,[:space:]]|$)"

# 双向自检。单向不够：第一版只验了「抓得到违规」，于是漏掉了反方向的错，
# 静默放行了一个真违规。两个方向都要验。
selftest() {
    local T; T="$(mktemp -d)"
    printf 'from PySide6 import QtCore\n' > "$T/violation.py"
    # 一份只是在**谈论** GUI 库的文档字串，不得被判成违规
    {
        printf '%s\n' 'MSG = "this layer does not import any GUI library"'
        printf '%s\n' '# PySide6 and SwiftUI front ends share these decisions'
    } > "$T/prose.py"
    local caught missed
    caught="$(grep -rnE "$1" "$T/violation.py" 2>/dev/null || true)"
    missed="$(grep -rnE "$1" "$T/prose.py" 2>/dev/null || true)"
    rm -rf "$T"
    if [ -z "$caught" ]; then
        echo "${RED}自检失败：真违规没被抓到，闸门会静默放行——结果不可信${OFF}" >&2
        return 1
    fi
    if [ -n "$missed" ]; then
        echo "${RED}自检失败：谈论 GUI 库的散文被误判成违规，闸门会乱叫${OFF}" >&2
        return 1
    fi
    return 0
}

# 排除模式不能用 ^ 锚定：grep -rn 的输出带 `文件名:行号:` 前缀，
# 锚在行首的模式永远匹配不到那之后的 import。用 : 开头接受这个前缀。
# 允许集照抄已上架的 GasDyn 的 AST 版纪律测试：math、enum、__future__、
# 以及本包自身（相对或绝对都算）。
#
# 这一版之前只允许 math 与相对 import，拿去跑已上架的 GasDyn 会报七条
# 违规，而那七条全是对的写法：`import enum`（给流态枚举用）与
# `from gasdyn.kernel import isentropic`（同层兄弟模块）。
# **一个会对已知正确的代码报红的闸门，就是一个即将被关掉的闸门。**
PKGNAME="$(basename "$PKG")"
ALLOWED=":[[:space:]]*(import|from)[[:space:]]+(math([[:space:]]|$)|enum([[:space:]]|$)|__future__[[:space:]]|${PKGNAME}[.[:space:]]|\\.)"

# kernel 侧的双向自检。两个方向都要验，理由与上面那条一致。
kernel_selftest() {
    local T; T="$(mktemp -d)"
    printf 'import numpy as np\n' > "$T/violation.py"
    {
        printf '%s\n' 'from __future__ import annotations'
        printf '%s\n' 'import math'
        printf '%s\n' 'from . import limits'
        printf '%s\n' '    the value returned'
        printf '%s\n' '    from :func:`other` is undefined here.'
    } > "$T/clean.py"
    local caught missed
    caught="$(grep -rnE "$IMPORT" "$T/violation.py" 2>/dev/null | grep -vE "$ALLOWED" || true)"
    missed="$(grep -rnE "$IMPORT" "$T/clean.py" 2>/dev/null | grep -vE "$ALLOWED" || true)"
    rm -rf "$T"
    if [ -z "$caught" ]; then
        echo "${RED}自检失败：kernel 的真违规（import numpy）没被抓到${OFF}" >&2
        return 1
    fi
    if [ -n "$missed" ]; then
        echo "${RED}自检失败：__future__ / 同包相对 import / docstring 散文被误判${OFF}" >&2
        echo "$missed" | sed 's/^/    /' >&2
        return 1
    fi
    return 0
}

selftest "$UI_PATTERN" || exit 2
kernel_selftest || exit 2

echo
echo "${BOLD}架构不变量 1 · kernel 零依赖${OFF}"
HITS="$(grep -rnE "${IMPORT}" "$PKG/kernel" --include="*.py" 2>/dev/null \
        | grep -vE "$ALLOWED" || true)"
if [ -n "$HITS" ]; then
    echo "  ${RED}✗${OFF} kernel 引入了 math 与本包之外的东西："
    echo "$HITS" | sed 's/^/      /'
    FAIL=$((FAIL+1))
else
    echo "  ${GREEN}✓${OFF} 只出现 math 与本包自身"
fi

echo
echo "${BOLD}架构不变量 2 · 四层不含平台代码${OFF}"
LAYER_HITS=""
for layer in kernel composition solve dimension; do
    [ -d "$PKG/$layer" ] || continue
    H="$(grep -rnE "$PLATFORM" "$PKG/$layer" --include="*.py" 2>/dev/null || true)"
    [ -n "$H" ] && LAYER_HITS="${LAYER_HITS}${H}"$'\n'
done
if [ -n "$LAYER_HITS" ]; then
    echo "  ${RED}✗${OFF} 四层里出现了平台代码："
    echo "$LAYER_HITS" | sed '/^$/d;s/^/      /'
    FAIL=$((FAIL+1))
else
    echo "  ${GREEN}✓${OFF} kernel / composition / solve / dimension 均无平台代码"
fi

echo
echo "${BOLD}ui 层无框架${OFF}"
UI_HITS="$(grep -rnE "$UI_PATTERN" "$PKG/ui" --include="*.py" 2>/dev/null || true)"
if [ -n "$UI_HITS" ]; then
    echo "  ${RED}✗${OFF} ui 决策层 import 了 GUI 库——它必须被两个前端共用："
    echo "$UI_HITS" | sed 's/^/      /'
    FAIL=$((FAIL+1))
else
    echo "  ${GREEN}✓${OFF} ui 决策层不含 GUI 库"
fi

echo
[ "$FAIL" -eq 0 ] && { echo "${GREEN}${BOLD}零依赖纪律通过。${OFF}"; echo; exit 0; }
echo "${RED}${BOLD}未通过：$FAIL 项。${OFF}"; echo; exit 1

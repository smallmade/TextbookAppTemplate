#!/bin/bash
# 防再分叉 —— 工具链只许有一份真身。
#
#   bash check_no_drift.sh <APP-Development 目录>
#
# 2026-08-29 的实况：五个 Claude Code 会话同时写同一个 Google Drive 文件夹，
# 四个项目各持一份 tools/ci 副本。副本里有两项真改进（docstring 误报的两处
# 修复、出货副本双复查），也有三份已经过期的旧版——**而没有任何东西在看这
# 件事**，直到有人问「strip_spec.py 从哪来」才发现。
#
# 统一之后，各项目的 tools/ci 是指向模板的符号链接。这道检查确认它还是。
#
# 2026-08-31 加一条【归属】纪律。这道检查扫的是整棵树，于是别的项目正在施工
# 的中间状态会让**本项目**的套件变红——而那既不是本项目的问题，也不该由本
# 项目去改另一个项目的目录。
#
# 所以：**只有自己那一格算失败，别人的算情报。** 每个项目各自跑这道闸门、
# 各自守自己的链接，树一级的视野保留下来但不再制造跨项目噪音。
# 传 --mine <项目名> 指出哪一格是自己的；不传就退回旧行为（全树都算失败），
# 因为一道默认更宽松的闸门是靠不住的。
#
# 要改工具：改模板里的真身，别在项目里就地改。真要就地试，试完提升回模板
# 再把链接接回去——沉淀不回去的改进，下一个项目享受不到，而且会静默过期。
set -uo pipefail
ROOT="${1:-.}"
MINE=""
if [ "${2:-}" = "--mine" ]; then MINE="${3:-}"; fi
RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; BOLD=$'\033[1m'; OFF=$'\033[0m'
TPL="TextbookAppTemplate/tools/ci"
FAIL=0

echo; echo "${BOLD}工具链单一真身${OFF}"
[ -d "$ROOT/$TPL" ] || { echo "  ${RED}✗${OFF} 找不到模板 $TPL" >&2; exit 2; }

for d in "$ROOT"/*/; do
    name="$(basename "$d")"
    [ "$name" = "TextbookAppTemplate" ] && continue
    [ -e "$d/tools/ci" ] || continue
    if [ -L "$d/tools/ci" ]; then
        # cd -P 直接进入链接并解析成物理路径。手工拼 dirname + readlink 容易
        # 错在相对路径的基准上——第一版就错在那里，把通的链接报成了分叉。
        target="$(cd -P "$d/tools/ci" 2>/dev/null && pwd -P)"
        want="$(cd -P "$ROOT/$TPL" && pwd -P)"
        if [ "$target" = "$want" ]; then
            echo "  ${GREEN}✓${OFF} $name  → 模板"
        elif [ -n "$MINE" ] && [ "$name" != "$MINE" ]; then
            echo "  ${YELLOW}−${OFF} $name  链接指向别处：$target（别的项目，仅情报）"
        else
            echo "  ${RED}✗${OFF} $name  链接指向别处：$target"; FAIL=$((FAIL+1))
        fi
    else
        n=$(ls "$d/tools/ci" 2>/dev/null | grep -v __pycache__ | wc -l | tr -d ' ')
        if [ -n "$MINE" ] && [ "$name" != "$MINE" ]; then
            echo "  ${YELLOW}−${OFF} $name  是【实体副本】（$n 个文件），不是链接"
            echo "        别的项目的事，由那边的套件报。这里只记一笔。"
            continue
        fi
        echo "  ${RED}✗${OFF} $name  是【实体副本】（$n 个文件），不是链接"
        echo "        副本会静默过期，也会让真改进沉淀不回模板。"
        echo "        比对差异：diff -r '$ROOT/$TPL' '$d/tools/ci'"
        echo "        改进先提升回模板，再：ln -sfn ../../TextbookAppTemplate/tools/ci '$d/tools/ci'"
        FAIL=$((FAIL+1))
    fi
done

# 备份目录只是提醒，不算失败——它们是统一时留下的，确认无用后手动删。
for b in "$ROOT"/*/tools/ci.local-backup-*; do
    [ -e "$b" ] || continue
    echo "  ${YELLOW}−${OFF} 遗留备份：${b#$ROOT/}（确认无用后删除）"
done

echo
[ "$FAIL" -eq 0 ] && { echo "${GREEN}${BOLD}工具链未分叉。${OFF}"; echo; exit 0; }
echo "${RED}${BOLD}发现 $FAIL 处分叉。${OFF}"; echo; exit 1

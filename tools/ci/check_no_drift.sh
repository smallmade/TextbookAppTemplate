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
#
# 2026-09-02（M-03）加一条【有意 vs 无意】的区分。
#
# StructureOne 把工具链改成 git submodule（`vendor/textbook-app-template`）
# 是 P0-1 的**有意决定**，而这道闸门把它报成一处分叉、判未通过。一道对着
# 一个已经做过的决定天天报红的闸门，两周之内会被人加进忽略名单——连同它
# 本来要抓的那些真分叉。
#
# 所以现在分两种输出：
#   * **有意的 submodule 形态** —— 项目自己在 ci.toml 里写 submodule_toolchain
#     = true，或者链接目标落在本项目的 vendor/ 里且那里是个 git submodule。
#     报告为 ⧉，**不判未通过**；但仍然印出真身与副本的实际差异条数，因为
#     「有意分叉」不等于「可以永远不同步」。
#   * **无意的实体副本分叉** —— 没人声明过，判未通过。这是原来的那条规则，
#     一个字没松。
set -uo pipefail
ROOT="${1:-.}"
MINE=""
if [ "${2:-}" = "--mine" ]; then MINE="${3:-}"; fi
RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; BLUE=$'\033[36m'
BOLD=$'\033[1m'; OFF=$'\033[0m'
TPL="TextbookAppTemplate/tools/ci"
FAIL=0
SEEN=0
DELIBERATE=0

# 这个项目【声明过】它有意持有一份副本吗？
declared_submodule() {
    local dir="$1"
    [ -f "$dir/ci.toml" ] || return 1
    grep -qE '^[[:space:]]*submodule_toolchain[[:space:]]*=[[:space:]]*true' \
         "$dir/ci.toml"
}
# 或者：链接指向本项目自己的 vendor/，而那里确实是个 submodule。
# 判据是 .gitmodules 里真的有这一条——不是「路径里有 vendor 三个字母」。
#
# 两侧都先解析成物理路径再比。第一版拿 `./StructureOne/` 去前缀匹配一个
# 绝对路径，永远不成立，于是有意的 submodule 仍然被报成分叉。
is_vendored_submodule() {
    local dir="$1" target="$2"
    local here; here="$(cd -P "$dir" 2>/dev/null && pwd -P)" || return 1
    case "$target" in "$here"/vendor/*) ;; *) return 1 ;; esac
    [ -f "$dir/.gitmodules" ] || return 1
    grep -q "vendor/" "$dir/.gitmodules"
}

# 2026-09-03 加【单项目模式】。
#
# 这道闸门原本只有一种工作方式：站在 APP-Development 那一层，把各款 App 的
# tools/ci 一格一格看过去。而 **CI 上根本没有那一层**——工作流只 checkout 本
# 仓库加 submodule，`${ROOT}/TextbookAppTemplate/tools/ci` 不存在，于是它
# `exit 2`；退出码 2 又没带「尚不适用」，runner 只能判未通过。一道在 CI 上
# 永远红、而红的原因与它要查的事无关的闸门，两周之内会被人关掉。
#
# 这与同一轮修掉的 tools/icon 是同一个形状：**一个只在负责人那台机器上成立
# 的仓库外路径**。修法也一样——真身在本项目内部就有一份，就是 submodule。
#
# 所以模板不在时不再直接死掉，改为只看自己这一格，判据换成在任何机器上都
# 成立的那条：tools/ci 是符号链接（实体副本会静默过期），且解析得到、落在
# **本项目内部**（CI 与全新 clone 上也到得了）。
#
# 树一级的视野一点没减：模板在时，下面那段循环一个字都没改——已用真实的
# APP-Development 树对照过，改前改后输出逐字节相同。
single_project() {
    local dir here base nm target k fail=0
    if [ -n "${MINE}" ] && [ -d "${ROOT}/${MINE}" ]; then
        dir="${ROOT}/${MINE}"
    else
        dir="${ROOT}"
    fi
    here="$(cd -P "${dir}" 2>/dev/null && pwd -P)" || {
        echo "  ${RED}✗${OFF} 进不去 ${dir}" >&2; return 1; }
    base="$(basename "${here}")"

    echo "  ${YELLOW}−${OFF} 树一级没有 ${TPL} —— 只看本项目这一格（${base}）"
    echo "        CI 与全新 clone 上本来就只有本仓库加 submodule，那一层不存在。"

    if [ ! -e "${here}/tools/ci" ] && [ ! -L "${here}/tools/ci" ]; then
        echo "  ${RED}✗${OFF} 本项目没有 tools/ci —— 这不是「干净」，是没检查"
        echo
        echo "CHECKED n=0 unit=个项目的 tools/ci  —— 单项目模式，一格都没看到"
        return 1
    fi

    if [ -L "${here}/tools/ci" ]; then
        if target="$(cd -P "${here}/tools/ci" 2>/dev/null && pwd -P)"; then
            case "${target}" in
                "${here}"/*)
                    echo "  ${GREEN}✓${OFF} tools/ci  → ${target#"${here}"/}（本项目内）" ;;
                *)
                    echo "  ${RED}✗${OFF} tools/ci  指到仓库外：${target}"
                    echo "        仓库外的路径只在负责人那台机器上成立，CI 上它是悬空的。"
                    echo "        改成指进本项目的 vendor/："
                    echo "        ln -sfn ../vendor/textbook-app-template/tools/ci '${here}/tools/ci'"
                    fail=1 ;;
            esac
        else
            echo "  ${RED}✗${OFF} tools/ci  **悬空**：$(readlink "${here}/tools/ci")"
            echo "        解析不到。本机能用往往只因为仓库外恰好躺着那个目录。"
            fail=1
        fi
    else
        k="$(ls "${here}/tools/ci" 2>/dev/null | grep -v __pycache__ | wc -l | tr -d ' ')"
        if declared_submodule "${here}"; then
            echo "  ${BLUE}⧉${OFF} tools/ci  【有意】持有实体副本（${k} 个文件）"
        else
            echo "  ${RED}✗${OFF} tools/ci  是【无意的实体副本】（${k} 个文件），不是链接"
            echo "        副本会静默过期，也会让真改进沉淀不回模板。"
            fail=1
        fi
    fi

    # tools/ 下其余符号链接。**不是本闸门的判据**（判据是 tools/ci），但指到
    # 仓库外或悬空的一律点名：tools/icon 就是这样悬空了好几天——本机恰好有
    # 那个兄弟目录，CI 上没有，而在「全部闸门」被建包挡住的那几天里，没有
    # 任何东西在看它。
    for l in "${here}"/tools/*; do
        [ -L "${l}" ] || continue
        nm="tools/$(basename "${l}")"
        [ "${nm}" = "tools/ci" ] && continue
        if target="$(cd -P "${l}" 2>/dev/null && pwd -P)"; then
            case "${target}" in
                "${here}"/*)
                    echo "  ${GREEN}✓${OFF} ${nm}  → ${target#"${here}"/}（本项目内）" ;;
                *)
                    echo "  ${YELLOW}−${OFF} ${nm}  指到仓库外：${target}"
                    echo "        本机成立、CI 上悬空。不判本闸门未通过（判据是 tools/ci），"
                    echo "        但它迟早会以「文件找不到」的形式咬人。" ;;
            esac
        else
            echo "  ${YELLOW}−${OFF} ${nm}  **悬空**：$(readlink "${l}")"
            echo "        同上：不判未通过，但 CI 上它到不了。"
        fi
    done

    echo
    echo "CHECKED n=1 unit=个项目的 tools/ci  —— 单项目模式（树一级没有模板），只看了本项目这一格"
    [ "${fail}" -eq 0 ] && {
        echo "${GREEN}${BOLD}本项目的工具链指向本项目内部的真身。${OFF}"; echo; return 0; }
    echo "${RED}${BOLD}未通过：本项目的 tools/ci 到不了。${OFF}"; echo; return 1
}

echo; echo "${BOLD}工具链单一真身${OFF}"
[ -d "${ROOT}/${TPL}" ] || { single_project; exit $?; }

for d in "$ROOT"/*/; do
    name="$(basename "$d")"
    [ "$name" = "TextbookAppTemplate" ] && continue
    [ -e "$d/tools/ci" ] || continue
    SEEN=$((SEEN+1))
    if [ -L "$d/tools/ci" ]; then
        # cd -P 直接进入链接并解析成物理路径。手工拼 dirname + readlink 容易
        # 错在相对路径的基准上——第一版就错在那里，把通的链接报成了分叉。
        target="$(cd -P "$d/tools/ci" 2>/dev/null && pwd -P)"
        want="$(cd -P "$ROOT/$TPL" && pwd -P)"
        if [ "$target" = "$want" ]; then
            echo "  ${GREEN}✓${OFF} $name  → 模板"
        elif declared_submodule "$d" || is_vendored_submodule "$d" "$target"; then
            diffs="$(diff -rq "$want" "$target" 2>/dev/null \
                     | grep -v __pycache__ | wc -l | tr -d ' ')"
            DELIBERATE=$((DELIBERATE+1))
            echo "  ${BLUE}⧉${OFF} $name  【有意】以 submodule 持有副本：$target"
            echo "        与真身相差 $diffs 处。有意分叉 ≠ 可以永远不同步——"
            echo "        真身改动后要在那边同步一次：diff -r '$want' '$target'"
        elif [ -n "$MINE" ] && [ "$name" != "$MINE" ]; then
            echo "  ${YELLOW}−${OFF} $name  链接指向别处：${target}（别的项目，仅情报）"
        else
            echo "  ${RED}✗${OFF} $name  链接指向别处：$target"
            echo "        没有人声明过这是有意的。有意就在 $name/ci.toml 里写"
            echo "        submodule_toolchain = true，并说明谁负责同步。"
            FAIL=$((FAIL+1))
        fi
    else
        n=$(ls "$d/tools/ci" 2>/dev/null | grep -v __pycache__ | wc -l | tr -d ' ')
        if declared_submodule "$d"; then
            DELIBERATE=$((DELIBERATE+1))
            echo "  ${BLUE}⧉${OFF} $name  【有意】持有实体副本（$n 个文件）"
            continue
        fi
        if [ -n "$MINE" ] && [ "$name" != "$MINE" ]; then
            echo "  ${YELLOW}−${OFF} $name  是【实体副本】（$n 个文件），不是链接"
            echo "        别的项目的事，由那边的套件报。这里只记一笔。"
            continue
        fi
        echo "  ${RED}✗${OFF} $name  是【无意的实体副本】（$n 个文件），不是链接"
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
echo "CHECKED n=$SEEN unit=个项目的 tools/ci  —— 本次检查了 $SEEN 个项目的 tools/ci（其中 $DELIBERATE 处是有意的 submodule 形态）"
if [ "$SEEN" -eq 0 ]; then
    echo "  ${RED}✗${OFF} 一个项目的 tools/ci 都没看到——参数给的是 APP-Development 目录吗？"
    echo "     用法：bash check_no_drift.sh <APP-Development 目录> [--mine <项目名>]"
    exit 1
fi
[ "$FAIL" -eq 0 ] && { echo "${GREEN}${BOLD}工具链无【无意的】分叉。${OFF}"; echo; exit 0; }
echo "${RED}${BOLD}发现 $FAIL 处无意的分叉。${OFF}"; echo; exit 1

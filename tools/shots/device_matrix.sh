#!/usr/bin/env bash
# [M-C1] 设备矩阵采集 —— 一条命令，把每个画面在每一档设备尺寸、每一种
# 明暗外观下各拍一张，产出可评审的证据。规范 v5.0 §7.1 / Gate M4。
#
#   bash tools/shots/device_matrix.sh                 # 跑满矩阵
#   bash tools/shots/device_matrix.sh --dry-run       # 只算格数，不启动任何 App
#   bash tools/shots/device_matrix.sh --mac-only
#   bash tools/shots/device_matrix.sh --ipad-only --headless
#   bash tools/shots/device_matrix.sh --devices mac-default-window --screens 3
#   bash tools/shots/device_matrix.sh --self-test     # 守卫真的在工作吗
#
# 产物：build/device-matrix/<日期>/
#   <device>__<screen>__<appearance>.png   ← 闸门认的三段命名
#   _manifest.tsv / manifest.json          ← 每一格的机器记录（含实测尺寸）
#   _probe/                                ← 本机放不下的档留的实测图，
#                                            **文件名里没有设备名**，
#                                            所以闸门不会把它当成那一格的证据
#
# 三款 App 共用：设备清单、画面清单、外观清单全部读项目根的 ci.toml，
# 这个文件里没有任何一款 App 的名字。换一款 App 只要那份 ci.toml 是对的。
#
# ## 为什么有 --self-test
#
# 「没找到问题就算通过」的检查必须有一个已知会失败的样本证明它真的在工作。
# 这个工具的守卫全是这一类：锁屏守卫、切屏核对、探针命名。Gate S 那一版
# 脚本的教训是原话——一道静默放行的闸门比没有闸门更糟，没有闸门时你至少
# 知道自己没检查。
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=matrix_common.sh
source "$ROOT/tools/shots/matrix_common.sh"
MATRIX_ROOT="$ROOT"

OUT=""; DO_MAC=1; DO_IPAD=1; DRY=0; SELFTEST=0
PASS_ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --out)       OUT="$2"; shift 2 ;;
        --mac-only)  DO_IPAD=0; shift ;;
        --ipad-only) DO_MAC=0; shift ;;
        --dry-run)   DRY=1; shift ;;
        --self-test) SELFTEST=1; shift ;;
        --devices|--screens) PASS_ARGS+=("$1" "$2"); shift 2 ;;
        --headless)  PASS_ARGS+=("$1"); shift ;;
        -h|--help)   sed -n '2,30p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "不认识的参数：$1（--help 看用法）" >&2; exit 2 ;;
    esac
done
OUT="${OUT:-$ROOT/build/device-matrix/$(date +%F)}"

# ══════════════════════════════════════════════════════════════════════
# 自检：每一道守卫都要有一个已知会失败的样本
# ══════════════════════════════════════════════════════════════════════
if [ "$SELFTEST" = "1" ]; then
    echo "device_matrix.sh 自检"
    OK=0
    say() { if [ "$1" = "0" ]; then echo "  PASS  $2"; else echo "  FAIL  $2"; OK=1; fi; }

    # 1 · 锁屏守卫，对着一个【已知锁着】的样本
    matrix::_lock_probe() { echo '      "CGSSessionScreenIsLocked" => true'; }
    matrix::guard_unlocked >/dev/null 2>&1
    [ $? -ne 0 ]; say $? "抓到  锁着的会话（守卫会红）"

    # 2 · 同一道守卫，对着一个【已知没锁】的样本——只会红不会绿的守卫，
    #     等于把工具关掉
    matrix::_lock_probe() { echo '      "kCGSSessionOnConsoleKey" => true'; }
    matrix::guard_unlocked >/dev/null 2>&1
    say $? "放行  没锁的会话（守卫不会乱叫）"
    unset -f matrix::_lock_probe

    # 3 · 「18 张同一屏」的探测器
    T="$(mktemp -d)"
    printf 'aaa' > "$T/a.png"; printf 'aaa' > "$T/b.png"; printf 'zzz' > "$T/c.png"
    matrix::same_image "$T/a.png" "$T/b.png"
    say $? "抓到  两张逐字节相同的图（切屏失败的样子）"
    matrix::same_image "$T/a.png" "$T/c.png"
    [ $? -ne 0 ]; say $? "放行  两张不同的图"
    rm -rf "$T"

    # 4 · 命名：闸门认矩阵格的名字，不认探针的名字。
    #     判据不是「我觉得」，是拿闸门自己的 cell_files() 跑一遍。
    python3 - "$ROOT" <<'PY'
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(sys.argv[1]) / "tools/ci"))
from check_device_matrix import cell_files
cell  = pathlib.Path("mac-default-window__columns__dark.png")
probe = pathlib.Path("_probe/probe-w2500h1030-columns-dark.png")
assert len(cell_files([cell],  "mac-default-window", "columns", "dark")) == 1
assert len(cell_files([probe], "mac-default-window", "columns", "dark")) == 0
PY
    say $? "对上  闸门认矩阵格名 / 不认探针名（拿 cell_files 实跑）"

    # 5 · 陈旧证据：上一轮留下的 PNG 不许被这一轮报成 ok。
    #     这一条是实测抓到的：采集在锁屏下第一台设备就够不着辅助功能桥、
    #     一张都没拍，而登记表照样报「ok 8」——那 8 行是照目录里已有的文件
    #     生成的。判据用 mtime，因为「文件存在」只说明有人拍过，不说明是刚才。
    T="$(mktemp -d)"
    (
        MATRIX_ROOT="$ROOT"; MATRIX_OUT="$T"; matrix::init >/dev/null
        OLD="$T/mac-default-window__columns__dark.png"
        printf 'old' > "$OLD"
        touch -t 202601010000 "$OLD"          # 明显早于本轮
        matrix::record ok mac-default-window columns dark 1180 800 1180 800 "$OLD" ""
        NEW="$T/mac-default-window__columns__light.png"
        printf 'new' > "$NEW"                 # 就是刚刚写的
        matrix::record ok mac-default-window columns light 1180 800 1180 800 "$NEW" ""
    )
    grep -q '^stale-evidence' "$T/_manifest.tsv"
    say $? "抓到  上一轮留下的图被报成本轮的 ok"
    [ "$(grep -c '^ok' "$T/_manifest.tsv")" = "1" ]
    say $? "放行  本轮真的拍出来的那一格"
    rm -rf "$T"

    # 6 · 清单不许是空的
    N_TIERS="$(matrix::tiers all | grep -c .)"
    N_SCREENS="$(matrix::screens | grep -c .)"
    [ "$N_TIERS" -gt 0 ] && [ "$N_SCREENS" -gt 0 ]
    say $? "读到  $N_TIERS 档 · $N_SCREENS 屏（零个不是通过）"

    python3 "$ROOT/tools/shots/shots_config.py" --self-test >/dev/null
    say $? "形状读取器自检（ci.toml 的 [shots]）"
    python3 "$ROOT/tools/shots/matrix_report.py" --self-test >/dev/null
    say $? "登记表报告自检"
    python3 "$ROOT/tools/ci/check_device_matrix.py" --self-test >/dev/null
    say $? "闸门自检（契约那一头）"

    [ "$OK" = "0" ] && echo && echo "自检通过——守卫确实在工作" \
                    || { echo; echo "自检失败"; }
    exit "$OK"
fi

# ══════════════════════════════════════════════════════════════════════
# 计划
# ══════════════════════════════════════════════════════════════════════
matrix::load_config || exit 1
N_SCREENS="$(matrix::screens | grep -c .)"
N_MAC="$(matrix::tiers mac  | grep -c . || true)"
N_IPAD="$(matrix::tiers ipad | grep -c . || true)"
N_APP="$(echo "$SHOTS_APPEARANCES" | wc -w | tr -d ' ')"
if [ "$N_SCREENS" -eq 0 ] || { [ "$N_MAC" -eq 0 ] && [ "$N_IPAD" -eq 0 ]; } \
   || [ "$N_APP" -eq 0 ]; then
    echo "✗ 清单是空的：$N_MAC 个 Mac 档 · $N_IPAD 个 iPad 档 · $N_SCREENS 屏 · $N_APP 种外观。" >&2
    echo "  零格不是通过——先把 ci.toml 修好：" >&2
    echo "  python3 tools/shots/shots_config.py --describe" >&2
    exit 1
fi

echo "══ 设备矩阵 ══"
echo "  档位     Mac $N_MAC · iPad ${N_IPAD}（读 ${SHOTS_DEVICES_FROM}）"
echo "  画面     ${N_SCREENS}（screens_kind = ${SHOTS_SCREENS_KIND}）"
echo "  外观     ${N_APP}（${SHOTS_APPEARANCES}）"
echo "  合计     $(( (N_MAC + N_IPAD) * N_SCREENS * N_APP )) 格"
echo "  产物     $OUT"

if [ "$DRY" = "1" ]; then
    echo
    matrix::tiers all | awk -F'\t' '{printf "  %-26s %-5s %5s×%-5s %s\n",
        $1, $2, $3, $4, ($8=="1" ? "手工档" : "")}'
    echo
    echo "（--dry-run：没有启动任何 App，没有建任何模拟器。）"
    exit 0
fi

MATRIX_OUT="$OUT"
matrix::init || exit 1
RC=0

# `"${PASS_ARGS[@]:-}"` 在数组为空时展开成【一个空字串】，子脚本会把它当成
# 一个不认识的参数、退 2，而退 2 之前锁屏守卫一次都没跑过——看日志像是
# 守卫放行了。`${a[@]+"${a[@]}"}` 是空数组下真的什么都不展开的写法。
if [ "$DO_MAC" = "1" ]; then
    echo
    bash "$ROOT/tools/shots/matrix_mac.sh" "$OUT" \
        ${PASS_ARGS[@]+"${PASS_ARGS[@]}"} || RC=1
fi
if [ "$DO_IPAD" = "1" ]; then
    echo
    bash "$ROOT/tools/shots/matrix_ipad.sh" "$OUT" \
        ${PASS_ARGS[@]+"${PASS_ARGS[@]}"} || RC=1
fi

echo
echo "══ 登记 ══"
python3 "$ROOT/tools/shots/matrix_report.py" "$OUT" || RC=1
echo
echo "══ 闸门 ══"
python3 "$ROOT/tools/ci/check_device_matrix.py" --root "$ROOT"
echo
echo "下一步：把评分表骨架贴进 docs/device-matrix.md 并【看图逐格打分】"
echo "  python3 tools/shots/matrix_report.py $OUT --table"
exit "$RC"

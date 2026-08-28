#!/bin/bash
# Gate 07 —— 站点五个 URL 必须全数回 200。
#   bash check_urls.sh <app-slug> [域名]
# 打包脚本会验证支持网址可达；离线打包可跳过，但提交前网址必须真的可达。
set -uo pipefail
SLUG="${1:-}"; HOST="${2:-https://smallmade.github.io}"
[ -n "$SLUG" ] || { echo "用法: bash check_urls.sh <app-slug> [域名]" >&2; exit 2; }
RED=$'\033[31m'; GREEN=$'\033[32m'; BOLD=$'\033[1m'; OFF=$'\033[0m'
FAIL=0
echo; echo "${BOLD}Gate 07 · 站点可达${OFF}"
for p in "" support.html privacy.html manual/ theory/; do
    code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "$HOST/$SLUG/$p" 2>/dev/null || echo 000)"
    if [ "$code" = "200" ]; then
        printf "  ${GREEN}✓${OFF} %-14s %s\n" "${p:-/}" "$code"
    else
        printf "  ${RED}✗${OFF} %-14s %s\n" "${p:-/}" "$code"; FAIL=$((FAIL+1))
    fi
done
echo
[ "$FAIL" -eq 0 ] && { echo "${GREEN}${BOLD}五个 URL 全通。${OFF}"; echo; exit 0; }
echo "${RED}${BOLD}$FAIL 个 URL 不可达 —— Support 与 Privacy 是 ASC 必填项。${OFF}"; echo; exit 1

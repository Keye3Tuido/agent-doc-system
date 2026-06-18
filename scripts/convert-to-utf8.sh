#!/bin/bash
#
# 将文件或目录下所有文本文件转换为 UTF-8 编码。
# - UTF-8 / US-ASCII 已兼容，跳过
# - 内容嗅探（null 字节 + 严格 UTF-8 校验）识别二进制
# - 原地写回保留权限/属主/inode
#
# 用法: ./convert-to-utf8.sh [路径]              默认为 $PWD
# 排除: UTF8_EXCLUDE_RE='正则' ./convert-to-utf8.sh
#

set -uo pipefail

ROOT="${1:-$PWD}"
SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
EXCLUDE_RE="${UTF8_EXCLUDE_RE:-(^|/)(node_modules|\.git|\.svn|\.hg|dist|build|out|target|\.cache|\.next|\.nuxt|\.idea|\.vscode|venv|__pycache__|\.pytest_cache|\.mypy_cache)(/|$)}"

[ -e "$ROOT" ] || { echo "错误: 路径不存在: $ROOT" >&2; exit 2; }

CONVERTED=0; SKIPPED=0; BINARY=0; FAILED=0

# 严格判定: 前 8KB 无 null 字节 且 全文是合法 UTF-8
is_text_utf8() {
    perl -e '
        use Encode qw(decode FB_CROAK);
        open(F,"<:raw",$ARGV[0]) || exit 1;
        read(F, my $head, 8192);
        exit 1 if $head =~ /\x00/;
        seek(F,0,0); local $/; my $all = <F>;
        eval { decode("UTF-8", $all, FB_CROAK) };
        exit($@ ? 1 : 0);
    ' "$1"
}

convert() {
    local f="$1" enc tmp
    enc=$(file -b --mime-encoding "$f" 2>/dev/null | tr -d '[:space:]')
    case "$enc" in
        utf-8|us-ascii)
            echo "[跳过] $f ($enc)"; ((SKIPPED++)) ;;
        binary|"")
            if is_text_utf8 "$f"; then
                echo "[跳过] $f (内容是 UTF-8，被误判为 ${enc:-未知})"; ((SKIPPED++))
            else
                echo "[二进制] $f"; ((BINARY++))
            fi ;;
        *)
            tmp=$(mktemp) || { ((FAILED++)); return; }
            if iconv -f "$enc" -t UTF-8 "$f" > "$tmp" 2>/dev/null && cat "$tmp" > "$f"; then
                echo "[转换] $f ($enc → UTF-8)"; ((CONVERTED++))
            else
                echo "[失败] $f ($enc → UTF-8)"; ((FAILED++))
            fi
            rm -f "$tmp" ;;
    esac
}

echo "扫描目标: $ROOT"
echo

while IFS= read -r -d '' f; do
    [[ "$f" =~ $EXCLUDE_RE ]] && continue
    [ "$f" -ef "$SELF" ] && continue
    convert "$f"
done < <(find "$ROOT" -type f -print0)

printf '\n已转换: %d\n已跳过: %d\n二进制: %d\n失败:   %d\n' \
    "$CONVERTED" "$SKIPPED" "$BINARY" "$FAILED"

exit $((FAILED > 0))

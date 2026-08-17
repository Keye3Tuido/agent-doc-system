#!/bin/bash
#
# 将文件或目录下所有文本文件规范化为 UTF-8 / 无 BOM / LF 换行。
#
# 设计原则：**默认不猜编码**。
#   本脚本的主用途（手册 §6 第 2 条）是 agent 写完文件后的兜底，此时目标编码必然是
#   UTF-8，不需要任何推断。而一旦推断就存在静默损坏的风险：字节层面区分 GBK 中文与
#   EUC-KR 韩文需要语料统计，任何启发式都有失败面。历史上本脚本用
#   `file --mime-encoding` 判编码，它把 GBK 判成 iso-8859-1，而 `iconv -f iso-8859-1`
#   对任意字节都"成功"，因此静默产出过不可逆乱码。
#
#   因此：
#     - 默认模式只修可确定的问题：BOM 剥离、CRLF → LF、孤立 CR → LF。
#       文件不是合法 UTF-8 时**拒绝改动**并以非零退出，提示用 --from 指定。
#     - --from <enc>  显式指定源编码，确定性转换。
#     - --guess       启用启发式推断（opt-in）。仅当能拿到脚本区独占证据
#                     （谚文 / 假名）或只有唯一候选成立时才判定，否则仍然拒绝。
#
# "合规"的定义与 doc-encoding-check.py 保持一致：合法 UTF-8 + 无 BOM + 无 CRLF + 无孤立 CR。
# 合法 UTF-8 中的控制字符（换页 \x0c、ESC \x1b 等）**不视为问题**。
#
# 用法:
#   ./convert-to-utf8.sh [路径]                默认为 $PWD
#   ./convert-to-utf8.sh --from gb18030 <路径>
#   ./convert-to-utf8.sh --guess <路径>
# 排除: UTF8_EXCLUDE_RE='正则' ./convert-to-utf8.sh
#
# 退出码: 0 = 无失败项；1 = 至少一个文件未能处理（该文件保持原样）。
#

set -uo pipefail

FROM_ENC=""
GUESS=0
ROOT=""

usage() {
    sed -n '2,29p' "$0" | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
    case "$1" in
        --from)
            [ $# -ge 2 ] && [ -n "$2" ] || {
                echo "错误: --from 需要非空编码名" >&2
                exit 2
            }
            FROM_ENC="$2"; shift 2 ;;
        --from=*)
            FROM_ENC="${1#*=}"
            [ -n "$FROM_ENC" ] || {
                echo "错误: --from 需要非空编码名" >&2
                exit 2
            }
            shift ;;
        --guess)  GUESS=1; shift ;;
        -h|--help)
            usage
            exit 0 ;;
        --)
            shift
            [ $# -le 1 ] || { echo "错误: 只能指定一个路径" >&2; exit 2; }
            ROOT="${1:-}"; [ $# -eq 0 ] || shift ;;
        -*)
            echo "错误: 未知参数: $1" >&2
            usage >&2
            exit 2 ;;
        *)
            [ -z "$ROOT" ] || { echo "错误: 只能指定一个路径" >&2; exit 2; }
            ROOT="$1"; shift ;;
    esac
done
[ -z "$FROM_ENC" ] || [ "$GUESS" = "0" ] || {
    echo "错误: --from 与 --guess 不能同时使用" >&2
    exit 2
}
ROOT="${ROOT:-$PWD}"

SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
EXCLUDE_RE="${UTF8_EXCLUDE_RE:-(^|/)(node_modules|\.git|\.svn|\.hg|dist|build|out|target|\.cache|\.next|\.nuxt|\.idea|\.vscode|venv|__pycache__|\.pytest_cache|\.mypy_cache)(/|$)}"

[ -e "$ROOT" ] || { echo "错误: 路径不存在: $ROOT" >&2; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo "错误: 需要 python3" >&2; exit 2; }

CONVERTED=0; SKIPPED=0; BINARY=0; FAILED=0

# 嗅探 + 规范化。
# argv: <src> <tmp_out> <from_enc|""> <guess:0|1>
# stdout: 单行 "<STATUS>\t<ENC>\t<DETAIL>"
#   STATUS ∈ BINARY | UNKNOWN | AMBIGUOUS | OK | FIX
# FIX 时把规范化后的 UTF-8 字节写入 <tmp_out>，由调用方原地覆盖以保留 inode。
PY_SNIFF='
import sys

src, tmp, from_enc, guess = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] == "1"

try:
    with open(src, "rb") as f:
        data = f.read()
except OSError as e:
    print("UNKNOWN\t-\t%s" % e.__class__.__name__)
    raise SystemExit(0)

if not data:
    print("OK\tempty\t")
    raise SystemExit(0)

# 显式 --from 代表调用者已确认文本编码，此时允许 UTF-16 等含 NUL 的文本。
if not from_enc and b"\x00" in data[:8192]:
    print("BINARY\t-\t")
    raise SystemExit(0)


def decode_strict(enc):
    """严格解码。合法即成立——不因控制字符否决，与 doc-encoding-check.py 对齐。"""
    try:
        return data.decode(enc)
    except (UnicodeDecodeError, LookupError):
        return None


# 脚本区独占块：谚文与假名是韩文/日文的排他性证据，汉字区为中日韩共享，不具排他性。
HANGUL = ((0xAC00, 0xD7A3), (0x1100, 0x11FF), (0x3130, 0x318F))
KANA = ((0x3040, 0x309F), (0x30A0, 0x30FF), (0x31F0, 0x31FF))
CJK = ((0x4E00, 0x9FFF),)
SHARED_PUNCT = ((0x3000, 0x303F), (0xFF00, 0xFFEF))


def in_blocks(o, blocks):
    return any(lo <= o <= hi for lo, hi in blocks)


def euckr_bytes_ok(buf):
    """真 EUC-KR 的字节结构校验：双字节序列的前导与后续字节都必须落在 0xA1-0xFE。

    Python 的 euc_kr 编解码器实际是 CP949/UHC 语义，会接受 0x81-0xA0 前导与
    ASCII 区后续字节，因而能"成功"解码日文 Shift_JIS（前导 0x82）和
    Big5（后续 0x40-0x7E）并产出貌似合理的谚文。此校验用来挡掉这类冒名。
    """
    i = 0
    n = len(buf)
    while i < n:
        b = buf[i]
        if b < 0x80:
            i += 1
            continue
        if not (0xA1 <= b <= 0xFE):
            return False
        if i + 1 >= n:
            return False
        if not (0xA1 <= buf[i + 1] <= 0xFE):
            return False
        i += 2
    return True


def profile(text):
    nonascii = [ord(c) for c in text if ord(c) > 127]
    if not nonascii:
        return {"n": 0, "hangul": 0.0, "kana": 0.0, "rare": 0}
    n = len(nonascii)
    return {
        "n": n,
        "hangul": sum(1 for o in nonascii if in_blocks(o, HANGUL)) / n,
        "kana": sum(1 for o in nonascii if in_blocks(o, KANA)) / n,
        "rare": sum(
            1 for o in nonascii
            if not (in_blocks(o, CJK) or in_blocks(o, SHARED_PUNCT)
                    or in_blocks(o, HANGUL) or in_blocks(o, KANA))
        ),
    }


enc = text = None
detail = ""

if from_enc:
    text = decode_strict(from_enc)
    if text is None:
        print("UNKNOWN\t%s\t指定编码解码失败" % from_enc)
        raise SystemExit(0)
    enc = from_enc
else:
    text = decode_strict("utf-8")
    if text is not None:
        enc = "utf-8"
    elif not guess:
        print("UNKNOWN\t-\t非 UTF-8；默认模式不推断，请用 --from <enc> 或 --guess")
        raise SystemExit(0)
    else:
        # 1) 脚本区独占证据：评估**全部**候选后取证据最强者。
        #    不能用「首个命中」——日文/中文文本在 euc_kr 下也可能解出足量谚文，
        #    先试韩文分支会把它们抢走。
        evidence = []
        for cand, key, thresh in (
            ("euc_kr", "hangul", 0.30),
            ("shift_jis", "kana", 0.20),
            ("euc_jp", "kana", 0.20),
        ):
            t = decode_strict(cand)
            if t is None:
                continue
            if cand == "euc_kr" and not euckr_bytes_ok(data):
                continue
            p = profile(t)
            if p[key] >= thresh:
                # 证据强度 = 独占块占比 - 落在共享/罕见区的比例，罕见字符是乱码的信号
                strength = p[key] - (p["rare"] / p["n"] if p["n"] else 0)
                evidence.append((strength, cand, t, "%s=%.2f rare=%d" % (key, p[key], p["rare"])))
        if evidence:
            evidence.sort(key=lambda e: -e[0])
            _, enc, text, detail = evidence[0]

        # 2) 无独占证据：只有所有成功候选得到同一文本时才能采用。
        #    多个不同结果一律拒绝，避免把合法 GBK/Big5 静默改成另一种乱码。
        if text is None:
            ok = []
            for cand in ("gb18030", "big5", "euc_kr", "shift_jis", "euc_jp", "cp1252", "latin_1"):
                t = decode_strict(cand)
                if t is not None:
                    ok.append((cand, t))
            distinct = {t for _, t in ok}
            if len(distinct) == 1 and ok:
                enc, text, detail = ok[0][0], ok[0][1], "唯一候选"
            elif ok:
                print("AMBIGUOUS\t-\t%d 个候选均成立且结果不同: %s"
                      % (len(distinct), ",".join(c for c, _ in ok)))
                raise SystemExit(0)

if text is None:
    print("UNKNOWN\t-\t无候选编码成立")
    raise SystemExit(0)

changes = []
if enc.replace("_", "-") not in ("utf-8", "empty"):
    changes.append("encoding")
if text.startswith("\ufeff"):
    text = text[1:]
    changes.append("bom")
if "\r\n" in text:
    text = text.replace("\r\n", "\n")
    changes.append("crlf")
if "\r" in text:
    text = text.replace("\r", "\n")
    changes.append("cr")

if not changes:
    print("OK\t%s\t%s" % (enc, detail))
    raise SystemExit(0)

try:
    with open(tmp, "wb") as f:
        f.write(text.encode("utf-8"))
except OSError as e:
    print("UNKNOWN\t%s\t写临时文件失败: %s" % (enc, e.__class__.__name__))
    raise SystemExit(0)

print("FIX\t%s\t%s" % (enc, ",".join(changes)))
'

convert() {
    local f="$1" tmp out status enc detail
    tmp=$(mktemp) || { echo "[失败] $f (无法创建临时文件)"; ((FAILED++)); return; }

    out=$(python3 -c "$PY_SNIFF" "$f" "$tmp" "$FROM_ENC" "$GUESS" 2>/dev/null)
    if [ -z "$out" ]; then
        echo "[失败] $f (嗅探进程异常)"; ((FAILED++)); rm -f "$tmp"; return
    fi

    IFS=$'\t' read -r status enc detail <<< "$out"

    case "$status" in
        BINARY)
            echo "[二进制] $f"; ((BINARY++)) ;;
        OK)
            echo "[跳过] $f (${enc}, 已合规)"; ((SKIPPED++)) ;;
        FIX)
            if cat "$tmp" > "$f"; then
                echo "[修复] $f (${enc} → UTF-8: ${detail})"; ((CONVERTED++))
            else
                echo "[失败] $f (写回失败)"; ((FAILED++))
            fi ;;
        AMBIGUOUS)
            echo "[失败] $f (编码有歧义，未做改动: ${detail})"; ((FAILED++)) ;;
        *)
            echo "[失败] $f (编码无法判定，未做改动: ${detail})"; ((FAILED++)) ;;
    esac

    rm -f "$tmp"
}

echo "扫描目标: $ROOT"
[ -n "$FROM_ENC" ] && echo "指定源编码: $FROM_ENC"
[ "$GUESS" = "1" ] && echo "已启用启发式推断 (--guess)"
echo

if [ -f "$ROOT" ]; then
    if [ "$ROOT" -ef "$SELF" ]; then
        echo "[跳过] $ROOT (脚本自身)"; SKIPPED=1
    else
        convert "$ROOT"
    fi
else
    while IFS= read -r -d '' f; do
        [[ "$f" =~ $EXCLUDE_RE ]] && continue
        [ "$f" -ef "$SELF" ] && continue
        convert "$f"
    done < <(find "$ROOT" -type f -print0)
fi

printf '\n[汇总] 已修复: %d  已跳过: %d  二进制: %d  失败: %d\n' \
    "$CONVERTED" "$SKIPPED" "$BINARY" "$FAILED"
[ "$FAILED" -gt 0 ] && echo "[汇总] 失败项均保持原样未改动；逐文件调用时退出码只反映该文件。"

exit $((FAILED > 0))

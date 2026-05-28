#!/usr/bin/env bash
# 一键跑全部单元测试。--full 时附加 snapshot 层（待补）。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TESTS="$ROOT/scripts/tests"

echo "==> doc-system regression suite"
echo "    project root: $ROOT"

failed=0
for t in "$TESTS"/unit/test_*.py; do
    name="$(basename "$t" .py)"
    echo "    running $name ..."
    if ! python3 "$t"; then
        echo "    FAIL: $name"
        failed=$((failed + 1))
    fi
done

if [[ "${1:-}" == "--full" ]]; then
    if [[ -d "$TESTS/snapshots" ]] && ls "$TESTS/snapshots"/*/ >/dev/null 2>&1; then
        echo "==> snapshot suite (待补)"
        echo "    NOTE: snapshot 标杆项目尚未配置；参见 tests/README.md"
    fi
fi

if [[ $failed -gt 0 ]]; then
    echo "==> $failed test(s) failed"
    exit 1
fi
echo "==> all unit tests passed"

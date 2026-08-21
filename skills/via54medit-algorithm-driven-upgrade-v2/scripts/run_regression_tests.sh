#!/bin/bash
# run_regression_tests.sh — 一键跑全部 42 测试
# 用法: bash scripts/run_regression_tests.sh

set -e

SCRIPTS_DIR="$HOME/.medit/scripts"
TESTS_DIR="$HOME/.medit/tests"

echo "=========================================="
echo "via54Medit v1.3.0 Regression Test Suite"
echo "=========================================="
echo ""
echo "📁 Scripts: $SCRIPTS_DIR"
echo "📁 Tests:   $TESTS_DIR"
echo ""

# 检查 PYTHONPATH
export PYTHONPATH="$SCRIPTS_DIR:$TESTS_DIR:$PYTHONPATH"

# 跑 pytest
echo "🚀 Running pytest..."
echo ""
python3 -m pytest "$TESTS_DIR/" \
    --tb=short \
    --rootdir="$TESTS_DIR" \
    -v

RESULT=$?

echo ""
echo "=========================================="
if [ $RESULT -eq 0 ]; then
    echo "✅ All tests passed"
else
    echo "❌ Some tests failed (exit: $RESULT)"
fi
echo "=========================================="

exit $RESULT

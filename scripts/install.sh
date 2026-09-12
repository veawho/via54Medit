#!/usr/bin/env bash
# ==============================================================================
# via54Medit 一键跨平台部署入口 (POSIX: macOS / Linux)
# 对标业界成熟方案 (hermes-agent / openclaw):
#   - 环境变量污染防御 (unset PYTHONPATH / PYTHONHOME)
#   - Python 3.10+ 自动嗅探与智能回退
#   - 统一参数透传至 scripts/bootstrap_device.py (如 --dry-run, --no-verify-llm 等)
# ==============================================================================
set -euo pipefail

# 1. 环境变量防污染隔离
unset PYTHONPATH 2>/dev/null || true
unset PYTHONHOME 2>/dev/null || true

# 2. 定位仓库根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/bootstrap_device.py" ]]; then
    REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
elif [[ -f "${SCRIPT_DIR}/scripts/bootstrap_device.py" ]]; then
    REPO_ROOT="${SCRIPT_DIR}"
else
    REPO_ROOT="$(pwd)"
fi

BOOTSTRAP="${REPO_ROOT}/scripts/bootstrap_device.py"
if [[ ! -f "${BOOTSTRAP}" ]]; then
    echo "[-] 错误: 未在 ${REPO_ROOT} 找到 scripts/bootstrap_device.py" >&2
    exit 1
fi

# 3. 寻找 Python 3.10+ 解释器
find_python() {
    local candidates=(
        "${PYTHON:-}"
        "python3.12"
        "python3.11"
        "python3.10"
        "python3"
        "python"
    )

    for cmd in "${candidates[@]}"; do
        if [[ -n "${cmd}" ]] && command -v "${cmd}" >/dev/null 2>&1; then
            # 校验版本是否 >= 3.10
            if "${cmd}" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
                command -v "${cmd}"
                return 0
            fi
        fi
    done
    return 1
}

PY_BIN="$(find_python || true)"
if [[ -z "${PY_BIN}" ]]; then
    echo "[-] 错误: 未检测到 Python >= 3.10 解释器。" >&2
    echo "    请先安装 Python 3.10+ 并加入 PATH。" >&2
    exit 1
fi

echo "==> 启动 via54Medit 一键就绪初始化..."
echo "    解释器: ${PY_BIN} ($("${PY_BIN}" --version 2>&1))"
echo "    仓库目录: ${REPO_ROOT}"

# 4. 执行底层统一引导脚本并透传所有参数
exec "${PY_BIN}" "${BOOTSTRAP}" "$@"

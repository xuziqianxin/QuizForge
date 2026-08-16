#!/usr/bin/env bash
# QuizForge 启动脚本(Unix / macOS)
# 用法: ./start.sh
# 自动探测已安装依赖的 Python,首次运行自动安装依赖。

set -e
cd "$(dirname "$0")"

PYEXE=""
for cand in python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then
        if "$cand" -c "import textual, requests, bs4, qrcode, Crypto" >/dev/null 2>&1; then
            PYEXE="$cand"
            break
        fi
    fi
done

# 兜底: 任意 Python(自动安装依赖)
if [ -z "$PYEXE" ]; then
    for cand in python3 python; do
        if command -v "$cand" >/dev/null 2>&1; then
            PYEXE="$cand"
            break
        fi
    done
fi

if [ -z "$PYEXE" ]; then
    echo "[错误] 未找到可用的 Python 解释器,请安装 Python 3.10+ 后重试。" >&2
    echo "或手动执行: pip install -r requirements.txt ; python main.py" >&2
    exit 1
fi

if ! "$PYEXE" -c "import textual, requests, bs4, qrcode, Crypto" >/dev/null 2>&1; then
    echo "首次运行,正在安装依赖(textual requests beautifulsoup4 qrcode pycryptodome)..."
    "$PYEXE" -m pip install -r requirements.txt
fi

echo "使用解释器: $PYEXE"
exec "$PYEXE" main.py
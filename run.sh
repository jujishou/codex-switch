#!/usr/bin/env bash
# main 分支:仓库原版,无 mac 修改 — 直接起 gui_ctk.py
# 用法:./run.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/src"

PY=""
for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1; then
    if "$c" -c "import tkinter" >/dev/null 2>&1; then
      PY="$c"; break
    fi
  fi
done

if [ -z "$PY" ]; then
  echo "错误:找不到带 tkinter 的 Python。请先运行 brew install python-tk@3.13" >&2
  exit 1
fi

need_install=0
for mod in tomlkit customtkinter; do
  "$PY" -c "import $mod" >/dev/null 2>&1 || need_install=1
done
if [ "$need_install" = "1" ]; then
  echo "首次运行,安装依赖 ..."
  "$PY" -m pip install --user --break-system-packages tomlkit customtkinter
fi

exec "$PY" gui_ctk.py

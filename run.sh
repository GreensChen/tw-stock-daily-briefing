#!/usr/bin/env bash
# crontab 啟動腳本
set -euo pipefail

cd "$(dirname "$0")"

# 用專案內的 venv
exec ./.venv/bin/python main.py

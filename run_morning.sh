#!/usr/bin/env bash
# 早報 (盤前快報) — crontab 8:30 用
set -euo pipefail
cd "$(dirname "$0")"
exec ./.venv/bin/python main.py --mode morning

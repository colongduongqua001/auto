#!/usr/bin/env bash
# Demo: AI tự mở Chromium, vào Hacker News, lấy 3 tiêu đề top, in numbered list.
# Dùng làm smoke test khi clone repo về.
set -e
cd "$(dirname "$0")"

TASK="${1:-Vào https://news.ycombinator.com, lấy chính xác 3 tiêu đề bài top, trả về dạng numbered list \"1. ... 2. ... 3. ...\"}"

uv run python main.py --max-steps 15 "$TASK"

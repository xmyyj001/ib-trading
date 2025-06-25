#!/bin/bash
# file: cloud-run/application/cmd.sh

set -e

echo ">>> Starting Xvfb on display ${DISPLAY}..."
# 确保 DISPLAY 环境变量被正确设置
/usr/bin/Xvfb "${DISPLAY:-:0}" -ac -screen 0 1024x768x16 +extension RANDR &

echo ">>> Starting Gunicorn web server..."
# Gunicorn 将在 Dockerfile 设置的 WORKDIR (/home/app) 中运行
# 它会自动寻找 main.py 文件和其中的 app 对象
gunicorn main:app --bind 0.0.0.0:8080 --timeout 600 --workers 1 --log-level debug
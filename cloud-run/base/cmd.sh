#!/bin/bash
# 开启错误立即退出
set -e

echo "Starting Xvfb (virtual display)..."
# 将 Xvfb 放到后台运行
Xvfb :0 -ac -screen 0 1024x768x16 +extension RANDR &

# 设置 DISPLAY 环境变量，让后续的 GUI 程序知道使用哪个虚拟屏幕
export DISPLAY=:0

echo "Starting gunicorn web server..."
# 启动 gunicorn。它会加载 main.py，
# main.py 中的 Environment 初始化会触发 IB Gateway 在后台启动。
exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app
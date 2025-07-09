#!/bin/bash
# =======================================================
# == FINAL GOLDEN SCRIPT: cmd.sh
# =======================================================
set -e

# 确保 PROJECT_ID 环境变量在 Python 应用程序中可用
export PROJECT_ID="${PROJECT_ID}"

echo ">>> Starting Xvfb on display :0..."
Xvfb :0 -screen 0 1024x768x24 &
export DISPLAY=:0

echo ">>> Starting IB Gateway in the background..."
# 将后台进程的日志重定向，以便调试
/opt/ibc/gatewaystart.sh > /tmp/gateway-startup.log 2>&1 &

# 给予 IB Gateway 充分的启动和登录时间
echo ">>> Waiting for IB Gateway to initialize (90 seconds)..."
sleep 90

echo ">>> Starting Gunicorn web server in the foreground..."
exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app
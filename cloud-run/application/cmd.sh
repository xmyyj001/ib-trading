#!/bin/bash

# 开启错误立即退出
set -e

# --- 1. 启动 Xvfb ---
# 这是运行任何 GUI 应用（如 IB Gateway）的先决条件
echo ">>> Starting Xvfb on display :0..."
# 我们在后台运行 Xvfb
Xvfb :0 -screen 0 1024x768x24 &

# --- 2. 手动启动 IB Gateway ---
# 我们明确指定工作目录，并确保所有环境变量都已设置
echo ">>> Starting IB Gateway in the background..."

# 设置 DISPLAY 环境变量，让 Java 应用知道使用哪个虚拟屏幕
export DISPLAY=:0

# 直接在后台调用 IBC 的启动脚本。
# 注意：我们不再依赖 Python 的 ib_insync 来启动它。
# 这里的路径是绝对路径，非常可靠。
# 我们将日志输出重定向到 stdout 和 stderr，以便在 Cloud Run 日志中看到它们。
/opt/ibc/gatewaystart.sh > /proc/1/fd/1 2>/proc/1/fd/2 &

# --- 3. 等待 Gateway 初始化 ---
# 给予 IB Gateway 足够的时间来启动和完成登录。
# 这个时间可能需要根据实际情况调整，30-45秒通常是比较安全的。
echo ">>> Waiting for IB Gateway to initialize (45 seconds)..."
sleep 45

# --- 4. 启动 Gunicorn Web 服务器 ---
# 这是容器的主进程，必须在前台运行 (不能带 &)
# exec 会让 Gunicorn 替换当前的 shell 进程，这是最佳实践。
echo ">>> Starting Gunicorn web server in the foreground..."
exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app
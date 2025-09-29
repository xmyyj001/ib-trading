#!/bin/bash
# =======================================================
# == FINAL PRODUCTION SCRIPT: cmd.sh
# =======================================================
set -e

# Ensure PROJECT_ID is available to the Python application
export PROJECT_ID="${PROJECT_ID}"

echo ">>> Starting Xvfb on display :0..."
Xvfb :0 -screen 0 1024x768x24 &
export DISPLAY=:0

echo ">>> Starting IB Gateway in the background..."
# Redirect gateway logs for potential debugging
/opt/ibc/gatewaystart.sh > /tmp/gateway-startup.log 2>&1 &

# Give the IB Gateway ample time to initialize and log in.
# The Python app has its own retry logic, but this initial sleep
# prevents the app from even starting until the gateway is likely ready.
echo ">>> Waiting for IB Gateway to initialize (90 seconds)..."
sleep 90

echo ">>> Starting Gunicorn web server in the foreground..."
# Use exec to make Gunicorn the main process (PID 1)
exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 -k uvicorn.workers.UvicornWorker main:app

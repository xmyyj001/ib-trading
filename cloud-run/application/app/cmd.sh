#!/bin/bash
set -e

export PROJECT_ID="${PROJECT_ID}"

echo ">>> Starting Xvfb..."
Xvfb :0 -screen 0 1024x768x24 &
export DISPLAY=:0

echo ">>> Starting IB Gateway..."
/opt/ibc/gatewaystart.sh > /tmp/gateway-startup.log 2>&1 &

echo ">>> Waiting for IB Gateway to initialize (90 seconds)..."
sleep 90

echo ">>> Starting Gunicorn web server..."
exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 -k uvicorn.workers.UvicornWorker main:app
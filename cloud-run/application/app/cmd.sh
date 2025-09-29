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
echo ">>> Waiting for IB Gateway to initialize (90 seconds)..."
sleep 90

echo ">>> Starting application via custom launcher..."
# Use exec to make the launcher the main process (PID 1)
exec python launcher.py

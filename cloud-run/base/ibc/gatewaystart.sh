#!/bin/bash

# =======================================================
# == FINAL DEFINITIVE VERSION v2: gatewaystart.sh
# =======================================================

set -x

# --- 1. 定义所有路径和参数 ---
TRADING_MODE=${TRADING_MODE:-paper}
TWSUSERID=${IB_USERNAME}
TWSPASSWORD=${IB_PASSWORD}

IBC_PATH="/opt/ibc"
TWS_PATH="/opt/ibgateway" # 这是我们在 Dockerfile 中定义的统一路径
LOG_PATH="/opt/ibc/logs"
JAVA_EXEC="/usr/bin/java"

# --- 2. 构建 Classpath ---
# 关键修复：我们现在知道所有 Jar 都在 TWS_PATH 下
CP="${TWS_PATH}/*:${IBC_PATH}/IBController.jar"

# --- 3. 构建 IBC 参数 ---
IBC_ARGS="TwsPath=${TWS_PATH} IbLoginId=${TWSUSERID} IbPassword=${TWSPASSWORD} TradingMode=${TRADING_MODE}"

# --- 4. 确保日志目录存在 ---
mkdir -p "${LOG_PATH}"

echo "--- [INFO] Preparing to launch IB Gateway directly via System Java ---"
echo "Java: ${JAVA_EXEC}"
echo "Classpath: ${CP}"
echo "IBC Args: ${IBC_ARGS}"
echo "----------------------------------------------------------------"

# --- 5. 直接执行 java 命令 ---
exec "${JAVA_EXEC}" \
    -cp "${CP}" \
    -Dlog.path="${LOG_PATH}/" \
    -Dibc.ini.path="${IBC_PATH}" \
    com.ib.controller.IBCoco \
    "${IBC_ARGS}"
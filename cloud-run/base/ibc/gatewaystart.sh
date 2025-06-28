#!/bin/bash

# =======================================================
# == FINAL DEFINITIVE VERSION v13: gatewaystart.sh
# == Direct Java Invocation with Verified Paths
# =======================================================

set -e
set -x

# --- 1. 定义所有路径和参数 ---
TRADING_MODE=${TRADING_MODE:-paper}
TWSUSERID=${IB_USERNAME}
TWSPASSWORD=${IB_PASSWORD}

IBC_PATH="/opt/ibc"
# TWS_PATH 会从 Dockerfile 的 ENV 中继承，现在是正确的 /root/ibgateway/1030
TWS_PATH=${TWS_PATH:-/root/ibgateway/1030}
LOG_PATH="/opt/ibc/logs"
JAVA_EXEC="/usr/bin/java"

# --- 2. 构建真正正确的 Classpath ---
# 基于我们 find 命令的发现：
# 1. IB Gateway 的所有 Jar 都在 TWS_PATH/jars/ 目录下
# 2. IBC 的核心 Jar 是 IBC.jar，位于 IBC_PATH 下
TWS_JARS=$(find "${TWS_PATH}/jars" -name '*.jar' -print | tr '\n' ':')
CP="${TWS_JARS}${IBC_PATH}/IBC.jar"

# --- 3. 构建 IBC 参数 ---
IBC_ARGS="TwsPath=${TWS_PATH} IbLoginId=${TWSUSERID} IbPassword=${TWSPASSWORD} TradingMode=${TRADING_MODE}"

# --- 4. 确保日志目录存在 ---
mkdir -p "${LOG_PATH}"

echo "--- [INFO] Launching IB Gateway via Direct Java Call (v13) ---"
echo "Classpath: ${CP}"

# --- 5. 直接执行 java 命令 ---
exec "${JAVA_EXEC}" \
    -cp "${CP}" \
    -Dlog.path="${LOG_PATH}/" \
    -Dibc.ini.path="${IBC_PATH}" \
    com.ib.controller.IBCoco \
    "${IBC_ARGS}"
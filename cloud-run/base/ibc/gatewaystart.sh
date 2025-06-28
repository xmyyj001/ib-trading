#!/bin/bash

# =======================================================
# == DEBUGGING VERSION of gatewaystart.sh
# =======================================================

# 开启详细模式，打印出每一行执行的命令
set -x

# 从环境变量获取配置，如果未设置则使用默认值
TWS_MAJOR_VRSN=${TWS_VERSION:-1030}
IBC_INI=${IBC_INI:-/opt/ibc/config.ini}
TRADING_MODE=${TRADING_MODE:-paper}
IBC_PATH=${IBC_PATH:-/opt/ibc}
TWS_PATH=${TWS_PATH:-/root/ibgateway}
TWS_SETTINGS_PATH=${TWS_SETTINGS_PATH:-/root/ibgateway}
LOG_PATH=${LOG_PATH:-/opt/ibc/logs}

# 从环境变量获取IB账户凭据
TWSUSERID=${IB_USERNAME}
TWSPASSWORD=${IB_PASSWORD}

# 确保日志目录存在
mkdir -p "${LOG_PATH}"

echo "--- Starting IB Gateway with the following parameters: ---"
echo "TWS Version: ${TWS_MAJOR_VRSN}"
echo "Trading Mode: ${TRADING_MODE}"
echo "User ID: ${TWSUSERID}"
echo "IBC Path: ${IBC_PATH}"
echo "TWS Path: ${TWS_PATH}"
echo "Log Path: ${LOG_PATH}"
echo "--------------------------------------------------------"


# --- 关键修复：移除 exec，直接调用 start.sh ---
# 我们不再使用 exec，这样脚本就不会替换掉当前的 shell
# 我们直接调用它，并等待它完成
"${IBC_PATH}/start.sh" \
    "${TWS_MAJOR_VRSN}" \
    "${TRADING_MODE}" \
    "${TWSUSERID}" \
    "${TWSPASSWORD}" \
    --ibc-ini="${IBC_INI}" \
    --tws-path="${TWS_PATH}" \
    --tws-settings-path="${TWS_SETTINGS_PATH}" \
    --log-path="${LOG_PATH}" \
    --onexit-error=true \
    --onexit-exec="${IBC_PATH}/stop.sh"

# 脚本执行到这里后，我们可以检查一下进程状态
echo "--- start.sh script has finished. Checking for Java processes... ---"
ps aux | grep java || echo "No Java process found."
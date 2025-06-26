#!/bin/bash

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

# 启动IB Gateway
# 使用 exec 替换当前 shell 进程，确保信号正确传递
exec "${IBC_PATH}/start.sh" \
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
# ===================================================================
# == FINAL DEFINITIVE VERSION v9: cloud-run/base/Dockerfile
# == Based on verified file structure from interactive debugging
# ===================================================================
FROM python:3.9-slim

ENV TWS_VERSION=1030
ENV TWS_PATH=/opt/ibgateway
ENV IBC_PATH=/opt/ibc
ENV LOG_PATH=/opt/ibc/logs
ENV DISPLAY=:0

# --- 1. 安装所有系统依赖 ---
RUN apt-get update && \
    apt-get install --no-install-recommends -y \
        wget unzip xvfb libxtst6 libxrender1 procps xterm xfonts-base openjdk-17-jre && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# --- 2. 安装 IB Gateway ---
RUN mkdir -p "${TWS_PATH}" && \
    wget -q -O /tmp/ibgw.sh https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh && \
    chmod +x /tmp/ibgw.sh && \
    # 安装到 TWS_PATH，并验证 jts.jar
    /tmp/ibgw.sh -q -dir "${TWS_PATH}" && \
    rm -f /tmp/ibgw.sh && \
    test -f "${TWS_PATH}/jts.jar" || (echo "FATAL: jts.jar not found!" && exit 1)

# --- 3. 下载并正确解压 IBC v3.22.0 ---
RUN mkdir -p "${IBC_PATH}" && \
    wget -q -O /tmp/IBC.zip https://github.com/IbcAlpha/IBC/releases/download/3.22.0/IBCLinux-3.22.0.zip && \
    unzip -o /tmp/IBC.zip -d "${IBC_PATH}" && \
    rm -f /tmp/IBC.zip && \
    # 验证核心的 IBC.jar 存在
    test -f "${IBC_PATH}/IBC.jar" || (echo "FATAL: IBC.jar not found after unzip!" && exit 1)

# --- 4. 复制我们自己的启动脚本和配置文件 ---
COPY ibc/gatewaystart.sh ${IBC_PATH}/gatewaystart.sh
COPY ibc/config.ini ${IBC_PATH}/config.ini
RUN chmod +x ${IBC_PATH}/gatewaystart.sh
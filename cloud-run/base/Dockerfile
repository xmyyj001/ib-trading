# ===================================================================
# == FINAL DEFINITIVE VERSION v12: cloud-run/base/Dockerfile
# == Adds the final xauth dependency for xvfb-run
# ===================================================================
FROM python:3.9-slim

ENV TWS_PATH=/opt/ibgateway
ENV IBC_PATH=/opt/ibc
ENV DISPLAY=:0

# --- 1. 安装所有系统依赖 ---
# 关键修复：添加 xauth 包
RUN apt-get update && \
    apt-get install --no-install-recommends -y \
        wget \
        unzip \
        xvfb \
        xauth \
        libxtst6 \
        libxrender1 \
        procps \
        xterm \
        xfonts-base \
        openjdk-17-jre \
        libgtk-3-0 \
        libasound2 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# --- 2. 安装 IB Gateway (现在它应该能成功运行) ---
RUN wget -O /tmp/ibgw.sh https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh && \
    chmod +x /tmp/ibgw.sh && \
    # 在 Xvfb 环境中运行安装程序
    xvfb-run --auto-servernum /tmp/ibgw.sh -dir "${TWS_PATH}" && \
    rm -f /tmp/ibgw.sh && \
    # 关键验证
    test -f "${TWS_PATH}/jts.jar" || (echo "FATAL: IB Gateway installation failed, jts.jar not found!" && exit 1)

# --- 3. 下载并正确解压 IBC v3.22.0 ---
RUN mkdir -p "${IBC_PATH}" && \
    wget -q -O /tmp/IBC.zip https://github.com/IbcAlpha/IBC/releases/download/3.22.0/IBCLinux-3.22.0.zip && \
    unzip -o /tmp/IBC.zip -d "${IBC_PATH}" && \
    rm -f /tmp/IBC.zip && \
    test -f "${IBC_PATH}/scripts/ibcstart.sh" || (echo "FATAL: ibcstart.sh not found!" && exit 1)

# --- 4. 复制我们自己的配置文件和启动脚本 ---
COPY ibc/config.ini ${IBC_PATH}/config.ini
COPY ibc/gatewaystart.sh ${IBC_PATH}/gatewaystart.sh
RUN chmod +x ${IBC_PATH}/*.sh && \
    chmod +x ${IBC_PATH}/scripts/*.sh && \
    chmod +x ${IBC_PATH}/gatewaystart.sh
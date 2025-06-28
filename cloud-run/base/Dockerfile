# ===================================================================
# == FINAL DEFINITIVE VERSION v13: cloud-run/base/Dockerfile
# == Uses true silent installation mode for the installer
# ===================================================================
FROM python:3.9-slim

ENV TWS_PATH=/opt/ibgateway
ENV IBC_PATH=/opt/ibc
ENV DISPLAY=:0

# --- 1. 安装所有系统依赖 ---
RUN apt-get update && \
    apt-get install --no-install-recommends -y \
        wget unzip xvfb xauth libxtst6 libxrender1 procps xterm xfonts-base openjdk-17-jre libgtk-3-0 libasound2 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# --- 2. 安装 IB Gateway (使用真正的静默模式) ---
# 关键修复：在安装命令中添加 -q 标志，这是 install4j 的标准静默模式参数
RUN wget -O /tmp/ibgw.sh https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh && \
    chmod +x /tmp/ibgw.sh && \
    # -q 标志告诉安装程序以无人值守模式运行，自动接受所有默认设置
    # 我们不再需要 xvfb-run，因为 -q 模式通常不需要图形环境
    /tmp/ibgw.sh -q -dir "${TWS_PATH}" && \
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
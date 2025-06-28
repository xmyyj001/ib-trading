# ===================================================================
# == FINAL DEFINITIVE VERSION v16: cloud-run/base/Dockerfile
# == Based on verified community best practices for IB Gateway installation
# ===================================================================
FROM python:3.9-slim

# --- 1. 定义所有环境变量 ---
# 关键修复：将 TWS_PATH 设置为经过验证的、真正的默认安装路径
ENV TWS_PATH=/root/Jts
ENV IBC_PATH=/opt/ibc
ENV DISPLAY=:0

# --- 2. 安装所有系统依赖 ---
RUN apt-get update && \
    apt-get install --no-install-recommends -y \
        wget unzip xvfb xauth libxtst6 libxrender1 procps xterm xfonts-base openjdk-17-jre libgtk-3-0 libasound2 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# --- 3. 安装 IB Gateway (最简单、最可靠的方式) ---
# 我们让安装程序以静默模式安装到它唯一的、真实的默认位置 /root/Jts
RUN wget -O /tmp/ibgw.sh https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh && \
    chmod +x /tmp/ibgw.sh && \
    # -q 标志确保无人值守安装
    /tmp/ibgw.sh -q && \
    rm -f /tmp/ibgw.sh && \
    # 关键验证：直接验证真正的默认路径下是否存在 jts.jar
    test -f "${TWS_PATH}/jts.jar" || (echo "FATAL: IB Gateway installation failed, jts.jar not found at default path /root/Jts!" && exit 1)

# --- 4. 下载并正确解压 IBC v3.22.0 ---
RUN mkdir -p "${IBC_PATH}" && \
    wget -q -O /tmp/IBC.zip https://github.com/IbcAlpha/IBC/releases/download/3.22.0/IBCLinux-3.22.0.zip && \
    unzip -o /tmp/IBC.zip -d "${IBC_PATH}" && \
    rm -f /tmp/IBC.zip && \
    test -f "${IBC_PATH}/scripts/ibcstart.sh" || (echo "FATAL: ibcstart.sh not found!" && exit 1)

# --- 5. 复制我们自己的配置文件和启动脚本 ---
COPY ibc/config.ini ${IBC_PATH}/config.ini
COPY ibc/gatewaystart.sh ${IBC_PATH}/gatewaystart.sh
RUN chmod +x ${IBC_PATH}/*.sh && \
    chmod +x ${IBC_PATH}/scripts/*.sh && \
    chmod +x ${IBC_PATH}/gatewaystart.sh
# ===================================================================
# == FINAL DEFINITIVE VERSION v10: cloud-run/base/Dockerfile
# == Robust installation with verification at every step
# ===================================================================
FROM python:3.9-slim

# --- 1. 定义所有环境变量 ---
ENV TWS_PATH=/opt/ibgateway
ENV IBC_PATH=/opt/ibc
ENV DISPLAY=:0

# --- 2. 安装所有系统依赖 ---
RUN apt-get update && \
    apt-get install --no-install-recommends -y \
        wget unzip xvfb libxtst6 libxrender1 procps xterm xfonts-base openjdk-17-jre && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# --- 3. 安装 IB Gateway (最稳健的方式) ---
# 我们不再使用 -q 静默安装，并加入严格的验证
RUN wget -O /tmp/ibgw.sh https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh && \
    chmod +x /tmp/ibgw.sh && \
    # 直接指定安装目录，并验证
    /tmp/ibgw.sh -dir "${TWS_PATH}" && \
    rm -f /tmp/ibgw.sh && \
    # 关键验证：确认核心的 jts.jar 文件现在存在于正确的位置！
    # 如果不存在，整个 Docker build 将会失败。
    test -f "${TWS_PATH}/jts.jar" || (echo "FATAL: IB Gateway installation failed, jts.jar not found!" && exit 1)

# --- 4. 下载并正确解压 IBC v3.22.0 ---
RUN mkdir -p "${IBC_PATH}" && \
    wget -O /tmp/IBC.zip https://github.com/IbcAlpha/IBC/releases/download/3.22.0/IBCLinux-3.22.0.zip && \
    unzip -o /tmp/IBC.zip -d "${IBC_PATH}" && \
    rm -f /tmp/IBC.zip && \
    # 关键验证：确认核心的 IBC.jar 存在
    test -f "${IBC_PATH}/IBC.jar" || (echo "FATAL: IBC.jar not found after unzip!" && exit 1)

# --- 5. 复制我们自己的配置文件和启动脚本 ---
COPY ibc/config.ini ${IBC_PATH}/config.ini
COPY ibc/gatewaystart.sh ${IBC_PATH}/gatewaystart.sh
# 关键修复：为所有需要执行的脚本添加权限
RUN chmod +x ${IBC_PATH}/*.sh && \
    chmod +x ${IBC_PATH}/scripts/*.sh && \
    chmod +x ${IBC_PATH}/gatewaystart.sh
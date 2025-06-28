# ===================================================================
# == FINAL DEFINITIVE VERSION v4: cloud-run/base/Dockerfile
# == Ensures complete and correct installation of all components
# ===================================================================
FROM python:3.9-slim

# --- 1. 定义所有环境变量 ---
ENV TWS_VERSION=1030
# 关键修改：使用一个更标准的、统一的安装路径
ENV TWS_PATH=/opt/ibgateway
ENV IBC_PATH=/opt/ibc
ENV LOG_PATH=/opt/ibc/logs
ENV DISPLAY=:0

# --- 2. 安装所有系统依赖 ---
# 一次性安装所有需要的包：Java, 图形库, 字体, 和系统工具
RUN apt-get update && \
    apt-get install --no-install-recommends -y \
        wget \
        unzip \
        xvfb \
        libxtst6 \
        libxrender1 \
        procps \
        xterm \
        xfonts-base \
        openjdk-17-jre && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# --- 3. 安装 IB Gateway ---
# 我们让安装脚本安装到它默认的位置，然后我们再移动它
RUN mkdir -p /root/Jts && \
    wget -q -O /tmp/ibgw.sh https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh && \
    chmod +x /tmp/ibgw.sh && \
    # 使用 -q 标志进行静默安装
    /tmp/ibgw.sh -q && \
    # 关键修改：将安装好的内容从默认的 ~/Jts 移动到我们期望的 /opt/ibgateway
    mv /root/Jts/* "${TWS_PATH}/" && \
    rm -f /tmp/ibgw.sh && \
    # 关键验证：确认核心的 Jar 文件现在存在于正确的位置
    test -f "${TWS_PATH}/jts.jar" || (echo "FATAL: jts.jar not found after installation!" && exit 1)

# --- 4. 安装 IBC (IB Controller) ---
RUN mkdir -p "${IBC_PATH}" && \
    wget -q -O "${IBC_PATH}/IBController.jar" https://github.com/IbcAlpha/IBC/releases/download/3.7.0/IBController-3.7.0.jar

# --- 5. 复制我们自己的配置文件和启动脚本 ---
COPY ibc/config.ini ${IBC_PATH}/config.ini
COPY ibc/gatewaystart.sh ${IBC_PATH}/gatewaystart.sh
RUN chmod +x ${IBC_PATH}/gatewaystart.sh
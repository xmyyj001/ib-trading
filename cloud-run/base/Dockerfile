# ===================================================================
# == FINAL DEFINITIVE VERSION v20: cloud-run/base/Dockerfile
# == Abandons all shell scripts, uses Direct Java Invocation
# ===================================================================
FROM python:3.9-slim

# --- 1. 定义所有环境变量 ---
ENV TWS_PATH=/root/ibgateway/1030
ENV IBC_PATH=/opt/ibc
ENV DISPLAY=:0

# --- 2. 安装所有系统依赖 ---
RUN apt-get update && \
    apt-get install --no-install-recommends -y \
        wget unzip xvfb xauth libxtst6 libxrender1 procps xterm xfonts-base openjdk-17-jre libgtk-3-0 libasound2 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# --- 3. 安装 IB Gateway (使用控制台模式并自动应答) ---
RUN wget -O /tmp/ibgw.sh https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh && \
    chmod +x /tmp/ibgw.sh && \
    (echo ""; echo "1"; echo ""; echo "") | /tmp/ibgw.sh -c && \
    rm -f /tmp/ibgw.sh && \
    # 验证最终路径下的核心 Jar 文件
    test -f "${TWS_PATH}/jars/jts.jar" || (echo "FATAL: jts.jar not found at ${TWS_PATH}/jars!" && exit 1)

# --- 4. 下载并正确解压 IBC v3.22.0 ---
RUN mkdir -p "${IBC_PATH}" && \
    wget -q -O /tmp/IBC.zip https://github.com/IbcAlpha/IBC/releases/download/3.22.0/IBCLinux-3.22.0.zip && \
    unzip -o /tmp/IBC.zip -d "${IBC_PATH}" && \
    rm -f /tmp/IBC.zip && \
    # 验证核心的 IBC.jar 存在
    test -f "${IBC_PATH}/IBC.jar" || (echo "FATAL: IBC.jar not found!" && exit 1)

# --- 5. 复制我们自己的配置文件和启动脚本 ---
COPY ibc/config.ini ${IBC_PATH}/config.ini
COPY ibc/gatewaystart.sh ${IBC_PATH}/gatewaystart.sh
RUN chmod +x ${IBC_PATH}/gatewaystart.sh
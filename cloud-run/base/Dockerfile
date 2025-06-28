# ===================================================================
# == FINAL DEFINITIVE VERSION v14: cloud-run/base/Dockerfile
# == Let installer use default path, then move files. This is the most robust way.
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

# --- 2. 安装 IB Gateway (最稳健的方式) ---
# 关键修复：我们让安装程序以静默模式安装到它的默认位置 /root/Jts
RUN wget -O /tmp/ibgw.sh https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh && \
    chmod +x /tmp/ibgw.sh && \
    # 运行静默安装，不指定 -dir 参数
    /tmp/ibgw.sh -q && \
    rm -f /tmp/ibgw.sh && \
    # 关键修复：在安装完成后，将所有文件从默认路径 /root/Jts 移动到我们期望的路径 /opt/ibgateway
    mkdir -p "${TWS_PATH}" && \
    mv /root/Jts/* "${TWS_PATH}/" && \
    # 关键验证：现在，我们再来验证 jts.jar 是否在我们期望的最终路径中
    test -f "${TWS_PATH}/jts.jar" || (echo "FATAL: jts.jar not found after moving!" && exit 1)

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
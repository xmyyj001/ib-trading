# ===================================================================
# == FINAL DEFINITIVE VERSION (For Cloud Build): cloud-run/base/Dockerfile
# ===================================================================
FROM python:3.9-slim

# ... (ENV 和系统依赖安装部分保持不变) ...
ENV TWS_PATH=/root/Jts/ibgateway/1030
ENV IBC_PATH=/opt/ibc
ENV DISPLAY=:0

RUN apt-get update && \
    apt-get install --no-install-recommends -y \
        xvfb xauth libxtst6 libxrender1 procps xterm xfonts-base openjdk-17-jre libgtk-3-0 libasound2 unzip && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# --- 3. 从构建上下文中的 local_deps 目录复制并安装 ---
COPY local_deps/ibgateway-stable-standalone-linux-x64.sh /tmp/ibgw.sh
RUN chmod +x /tmp/ibgw.sh && \
    (echo ""; echo "1"; echo ""; echo "") | /tmp/ibgw.sh -c && \
    rm -f /tmp/ibgw.sh && \
    test -d "${TWS_PATH}/jars" || (echo "FATAL: IB Gateway installation failed!" && exit 1)

# --- 4. 从构建上下文中的 local_deps 目录复制并解压 ---
RUN mkdir -p "${IBC_PATH}"
COPY local_deps/IBController.zip /tmp/IBC.zip
RUN unzip -o /tmp/IBC.zip -d "${IBC_PATH}" && \
    rm -f /tmp/IBC.zip && \
    test -f "${IBC_PATH}/IBController.jar" || (echo "FATAL: IBController.jar not found!" && exit 1)

# --- 5. 复制我们自己的配置文件和启动脚本 ---
COPY ibc/config.ini ${IBC_PATH}/config.ini
COPY ibc/gatewaystart.sh ${IBC_PATH}/gatewaystart.sh
RUN chmod +x ${IBC_PATH}/gatewaystart.sh
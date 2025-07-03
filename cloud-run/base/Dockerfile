# ===================================================================
# == FINAL GOLDEN VERSION: cloud-run/base/Dockerfile
# ===================================================================
FROM python:3.9-slim

# --- 1. 定义所有环境变量 ---
# 关键：TWS_PATH 设置为经过验证的、真正的顶层安装路径
ENV TWS_PATH=/root/Jts
ENV IBC_PATH=/opt/ibc
ENV DISPLAY=:0

# --- 2. 安装所有系统依赖 ---
# 我们不再需要自己安装 Java，因为安装程序会自带
RUN apt-get update && \
    apt-get install --no-install-recommends -y \
        wget unzip xvfb xauth libxtst6 libxrender1 procps xterm xfonts-base libgtk-3-0 libasound2 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# --- 3. 安装 IB Gateway (使用经过验证的控制台模式) ---
RUN wget -O /tmp/ibgw.sh https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh && \
    chmod +x /tmp/ibgw.sh && \
    # 使用自动应答来完成控制台安装
    (echo ""; echo "1"; echo ""; echo "") | /tmp/ibgw.sh -c && \
    rm -f /tmp/ibgw.sh && \
    # 验证安装是否成功
    test -d "${TWS_PATH}/ibgateway/1030/jars" || (echo "FATAL: IB Gateway installation failed!" && exit 1)

# --- 4. 下载并正确解压 IBC v3.22.0 ---
RUN mkdir -p "${IBC_PATH}" && \
    wget -q -O /tmp/IBC.zip https://github.com/IbcAlpha/IBC/releases/download/3.22.0/IBCLinux-3.22.0.zip && \
    unzip -o /tmp/IBC.zip -d "${IBC_PATH}" && \
    rm -f /tmp/IBC.zip

# --- 5. 复制我们自己的配置文件和启动脚本 ---
COPY ibc/config.ini ${IBC_PATH}/config.ini
COPY ibc/gatewaystart.sh ${IBC_PATH}/gatewaystart.sh
# 关键：为所有需要执行的脚本添加权限
RUN chmod +x ${IBC_PATH}/*.sh && \
    chmod +x ${IBC_PATH}/scripts/*.sh && \
    chmod +x ${IBC_PATH}/gatewaystart.sh
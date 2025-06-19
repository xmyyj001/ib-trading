# 使用 Python 3.9 slim 作为基础镜像
FROM python:3.9-slim

# --- 1. 环境变量 ---
ENV TWS_VERSION=1030
ENV TWS_PATH=/root/ibgateway
ENV TWS_SETTINGS_PATH=/root/ibgateway
ENV IBC_PATH=/opt/ibc
ENV IBC_INI=${IBC_PATH}/config.ini
ENV DISPLAY=:0

# --- 2. 安装依赖与 IB Gateway ---
RUN apt-get update && apt-get install --no-install-recommends -y \
    wget \
    unzip \
    xvfb \
    libxtst6 \
    libxrender1 \
    openjdk-17-jre-headless \
    && apt-get clean && apt-get -y autoremove \
    \
    # 创建目录
    && mkdir -p ${TWS_PATH} ${IBC_PATH} /tmp \
    \
    # 下载并安装 IB Gateway
    && echo "正在下载 IB Gateway..." \
    && wget -q -O /tmp/ibgw.sh https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh \
    && chmod +x /tmp/ibgw.sh \
    \
    # 安装到版本化子目录
    && echo "正在将 IB Gateway 安装到 ${TWS_PATH}/${TWS_VERSION}..." \
    && /tmp/ibgw.sh -q -dir "${TWS_PATH}/${TWS_VERSION}" \
    && rm /tmp/ibgw.sh \
    \
    # 验证并创建符号链接
    && echo "正在验证安装..." \
    && ls -lR ${TWS_PATH} \
    && if [ ! -f "${TWS_PATH}/${TWS_VERSION}/jars/jts4launch-${TWS_VERSION}.jar" ]; then \
        echo "错误: 未找到核心文件 ${TWS_PATH}/${TWS_VERSION}/jars/jts4launch-${TWS_VERSION}.jar！" >&2; \
        exit 1; \
    fi \
    && echo "正在创建 jts.jar 符号链接..." \
    && ln -s "${TWS_PATH}/${TWS_VERSION}/jars/jts4launch-${TWS_VERSION}.jar" "${TWS_PATH}/${TWS_VERSION}/jars/jts.jar" \
    && echo "安装验证成功。" \
    \
    # 下载并安装 IBC
    && echo "正在下载并安装 IBC..." \
    && wget -q -O /tmp/IBC.zip https://github.com/IbcAlpha/IBC/releases/download/3.12.0/IBCLinux-3.12.0.zip \
    && unzip /tmp/IBC.zip -d ${IBC_PATH} \
    && chmod +x ${IBC_PATH}/*.sh ${IBC_PATH}/*/*.sh \
    && rm /tmp/IBC.zip \
    \
    # --- 关键修正：确保这一段在 RUN 指令内部 ---
    && echo "正在复制 vmoptions 文件..." \
    && cp "${TWS_PATH}/${TWS_VERSION}/ibgateway.vmoptions" "${IBC_PATH}/ibgateway.vmoptions"

# --- 3. 复制配置文件 ---
COPY ibc/config.ini ${IBC_INI}
COPY ibc/jts.ini "${TWS_PATH}/${TWS_VERSION}/jts.ini"

# --- 4. 设置应用目录 ---
WORKDIR /home
COPY cmd.sh cmd.sh
RUN chmod +x cmd.sh

CMD tail -f /dev/null
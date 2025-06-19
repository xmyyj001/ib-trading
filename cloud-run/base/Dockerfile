# 使用 Python 3.9 slim 作为基础镜像
FROM python:3.9-slim

# --- 1. 环境变量 ---
# 将版本和路径统一定义，方便维护。
# 我们将按照 IBC 脚本的要求，把 IB Gateway 安装到一个带版本号的子目录里。
ENV TWS_VERSION=1030
# IB Gateway 相关文件的主要安装路径
ENV TWS_PATH=/root/ibgateway
# 用户设置文件的路径 (可以和 TWS_PATH 相同)
ENV TWS_SETTINGS_PATH=/root/ibgateway
# IBC 的安装路径
ENV IBC_PATH=/opt/ibc
# IBC 配置文件的路径
ENV IBC_INI=${IBC_PATH}/config.ini
# 为虚拟屏幕设置显示器
ENV DISPLAY=:0

# --- 2. 安装依赖与 IB Gateway ---
# 将所有安装步骤合并到单个 RUN 命令中，以优化镜像层的大小。
RUN apt-get update && apt-get install --no-install-recommends -y \
    wget \
    unzip \
    xvfb \
    libxtst6 \
    libxrender1 \
    openjdk-17-jre-headless \
    && apt-get clean && apt-get -y autoremove \
    \
    # 创建必要的目录
    && mkdir -p ${TWS_PATH} ${IBC_PATH} /tmp \
    \
    # 下载并安装 IB Gateway
    && echo "正在下载 IB Gateway..." \
    && wget -q -O /tmp/ibgw.sh https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh \
    && chmod +x /tmp/ibgw.sh \
    \
    # 关键修正：将 IBG 安装到一个带版本号的子目录中
    && echo "正在将 IB Gateway 安装到 ${TWS_PATH}/${TWS_VERSION}..." \
    && /tmp/ibgw.sh -q -dir "${TWS_PATH}/${TWS_VERSION}" \
    && rm /tmp/ibgw.sh \
    \
    # 关键验证：检查核心的 .jar 文件是否存在于正确的路径下
    && echo "正在验证安装..." \
    && ls -lR ${TWS_PATH} \
    && if [ ! -f "${TWS_PATH}/${TWS_VERSION}/jars/jts.jar" ]; then \
        echo "错误: 在 ${TWS_PATH}/${TWS_VERSION}/jars/ 中未找到 jts.jar 文件！" >&2; \
        exit 1; \
    fi \
    && echo "安装验证成功。" \
    \
    # 下载并安装 IBC (控制脚本)
    && echo "正在下载并安装 IBC..." \
    && wget -q -O /tmp/IBC.zip https://github.com/IbcAlpha/IBC/releases/download/3.12.0/IBCLinux-3.12.0.zip \
    && unzip /tmp/IBC.zip -d ${IBC_PATH} \
    && chmod +x ${IBC_PATH}/*.sh ${IBC_PATH}/*/*.sh \
    && rm /tmp/IBC.zip

# --- 3. 复制配置文件 ---
# 复制我们为 IBC 自定义的配置文件
COPY ibc/config.ini ${IBC_INI}
# 将 jts.ini 复制到带版本号的 IBG 安装目录内的正确位置
COPY ibc/jts.ini "${TWS_PATH}/${TWS_VERSION}/jts.ini"

# --- 4. 设置应用目录 ---
WORKDIR /home
COPY cmd.sh cmd.sh
RUN chmod +x cmd.sh

# 这个 CMD 只是用于创建基础镜像，应用层的 Dockerfile 会覆盖它。
CMD tail -f /dev/null
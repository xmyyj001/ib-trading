# --- START OF FINAL, PRODUCTION-READY DOCKERFILE ---

FROM python:3.9-slim

# --- 1. 设置环境变量 ---
# (此部分保持不变)
ENV TWS_VERSION=981
ENV twsPath=/root/ibgateway
ENV twsSettingsPath=/root/ibgateway
ENV TWS_INSTALL_LOG=/root/ibgateway/install.log
ENV ibcIni=/root/ibc/config.ini
ENV ibcPath=/opt/ibc
ENV javaPath=/usr/lib/jvm/java-17-openjdk-amd64/bin
ENV DISPLAY=:0

# --- 2. 最终的、正确的安装步骤 ---
RUN apt-get update && \
    export DEBIAN_FRONTEND=noninteractive && \
    apt-get install --no-install-recommends -y \
    wget unzip xvfb libxtst6 libxrender1 net-tools openjfx openjdk-17-jre-headless \
  && apt-get clean && rm -rf /var/lib/apt/lists/* \
  && mkdir -p /tmp ${ibcPath} ${twsPath} \
  && wget -q -O /tmp/ibgw.sh https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh \
  && chmod +x /tmp/ibgw.sh \
  && /tmp/ibgw.sh -q -dir ${twsPath} \
  && rm /tmp/ibgw.sh \
    #
    # --- 核心修正 ---
    # 我们现在知道主JAR文件的名字是 jts4launch-*.jar
    # 所以我们更新 find 命令来查找这个新的文件名模式。
  && echo "Verifying that 'jts4launch-*.jar' was extracted to ${twsPath}..." \
  && find ${twsPath} -name "jts4launch-*.jar" -print -quit | grep -q . \
    #
    # 下载并安装 IBC
  && wget -q -O /tmp/IBC.zip https://github.com/IbcAlpha/IBC/releases/download/3.12.0/IBCLinux-3.12.0.zip \
  && unzip /tmp/IBC.zip -d ${ibcPath} \
  && chmod +x ${ibcPath}/*.sh ${ibcPath}/*/*.sh \
  && rm /tmp/IBC.zip

# --- 3. 复制配置文件和脚本 ---
# (此部分保持不变)
COPY ibc/config.ini ${ibcIni}
# 关键：jts.ini 必须和 jts4launch-*.jar 在同一个目录下，所以我们把它复制到 ${twsPath}/jars/
# 注意：您的旧 Dockerfile 把它复制到了 ${twsPath}，这是不正确的。
COPY ibc/jts.ini ${twsPath}/jars/jts.ini

WORKDIR /home
COPY cmd.sh cmd.sh
RUN chmod +x cmd.sh

# --- 4. 最终的 CMD ---
# (此部分保持不变)
CMD tail -f /dev/null

# --- END OF FINAL, PRODUCTION-READY DOCKERFILE ---
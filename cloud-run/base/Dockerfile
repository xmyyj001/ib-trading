# --- START OF DEBUGGING DOCKERFILE ---

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

# --- 2. 修正后的、正确的安装步骤 (带调试) ---
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
    # --- 核心调试步骤 ---
    # 我们在这里列出安装目录的全部内容，以便查看 jts.jar 到底被放在了哪里。
    # "ls -laR" 会递归地列出所有文件和目录。
  && echo "--- DEBUG: Listing contents of ${twsPath} ---" \
  && ls -laR ${twsPath} \
  && echo "--- END DEBUG ---" \
    #
    # 关键验证 (我们暂时让它继续运行，以便看到上面的调试输出)
  && echo "Verifying that 'jts.jar' was extracted to ${twsPath}..." \
  && find ${twsPath} -name "jts.jar" -print -quit | grep -q . \
    # 下载并安装 IBC
  && wget -q -O /tmp/IBC.zip https://github.com/IbcAlpha/IBC/releases/download/3.12.0/IBCLinux-3.12.0.zip \
  && unzip /tmp/IBC.zip -d ${ibcPath} \
  && chmod +x ${ibcPath}/*.sh ${ibcPath}/*/*.sh \
  && rm /tmp/IBC.zip

# --- 3. 复制配置文件和脚本 ---
# (此部分保持不变)
COPY ibc/config.ini ${ibcIni}
COPY ibc/jts.ini ${twsPath}/jts.ini

WORKDIR /home
COPY cmd.sh cmd.sh
RUN chmod +x cmd.sh

# --- 4. 最终的 CMD ---
# (此部分保持不变)
CMD tail -f /dev/null

# --- END OF DEBUGGING DOCKERFILE ---
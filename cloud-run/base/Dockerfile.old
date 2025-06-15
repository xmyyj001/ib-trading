FROM python:3.9-slim

# --- 1. 设置环境变量 ---
# ！！！核心改变：我们不再依赖 IB Gateway 的 JRE，而是自己安装并硬编码 javaPath。
ENV TWS_VERSION=981
ENV twsPath=/root/Jts
ENV twsSettingsPath=/root/Jts
ENV TWS_INSTALL_LOG=/root/Jts/tws_install.log
ENV ibcIni=/root/ibc/config.ini
ENV ibcPath=/opt/ibc
ENV javaPath=/usr/lib/jvm/java-17-openjdk-amd64/bin
ENV DISPLAY=:0

# --- 2. 简化的、健壮的安装步骤 ---
# 将所有依赖安装合并，并加入了 openjdk-17-jre-headless
RUN apt-get update && apt-get install --no-install-recommends -y \
    wget \
    unzip \
    xvfb \
    libxtst6 \
    libxrender1 \
    net-tools \
    openjfx \
    openjdk-17-jre-headless \
  && apt-get clean && apt-get -y autoremove \
  # 创建目录
  && mkdir -p /tmp ${ibcPath} ${twsPath} \
  # 下载并运行安装程序
  && wget -q -O /tmp/ibgw.sh https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh \
  && chmod +x /tmp/ibgw.sh \
  && yes n | echo ${twsPath} | /tmp/ibgw.sh > ${TWS_INSTALL_LOG} || true \
  && rm /tmp/ibgw.sh \
  # 验证 IB Gateway 安装
  && echo "Verifying content of installation directory: ${twsPath}" \
  && ls -l ${twsPath} \
  # 下载并安装 IBC
  && wget -q -O /tmp/IBC.zip https://github.com/IbcAlpha/IBC/releases/download/3.12.0/IBCLinux-3.12.0.zip \
  && unzip /tmp/IBC.zip -d ${ibcPath} \
  && chmod +x ${ibcPath}/*.sh ${ibcPath}/*/*.sh \
  && rm /tmp/IBC.zip

# --- 3. 复制配置文件和脚本 ---
COPY ibc/config.ini ${ibcIni}
COPY ibc/jts.ini ${twsPath}/jts.ini

WORKDIR /home
COPY cmd.sh cmd.sh
RUN chmod +x cmd.sh

# --- 4. 最终的 CMD ---
CMD tail -f /dev/null
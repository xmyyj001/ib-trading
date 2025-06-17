FROM python:3.9-slim

# --- 1. 设置环境变量 ---
# 我们将把所有 IB Gateway 的文件都放在 /root/ibgateway 目录下
ENV TWS_VERSION=1030
ENV twsPath=/root/ibgateway
ENV twsSettingsPath=/root/ibgateway
ENV TWS_INSTALL_LOG=/root/ibgateway/install.log
ENV ibcIni=/root/ibc/config.ini
ENV ibcPath=/opt/ibc
ENV javaPath=/usr/lib/jvm/java-17-openjdk-amd64/bin
ENV DISPLAY=:0

# --- 2. 全新的、最可靠的安装步骤 ---
RUN apt-get update && apt-get install --no-install-recommends -y \
    wget unzip xvfb libxtst6 libxrender1 net-tools openjfx openjdk-17-jre-headless \
  && apt-get clean && apt-get -y autoremove \
  # 创建我们的目标目录
  && mkdir -p /tmp ${ibcPath} ${twsPath} \
  # 下载 IB Gateway 安装脚本
  && wget -q -O /tmp/ibgw.sh https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh \
  && chmod +x /tmp/ibgw.sh \
  # 核心改变：不再运行 .sh 脚本，而是直接用 unzip 解压它！
  # 我们需要找到 .sh 文件中实际数据的起始点，通常可以通过 'tail' 和一个偏移量来实现
  # 'skip=$(grep -a -b -m 1 '^PK' /tmp/ibgw.sh | cut -d ':' -f 1)' 找到 ZIP 头的偏移量
  # 'dd if=/tmp/ibgw.sh of=/tmp/ibgw.zip skip=$skip bs=1' 提取 ZIP 数据
  # 为了简化，我们直接使用 unzip 的一个强大功能，让它自己找 ZIP 头
  && bash /tmp/ibgw.sh -q -dir "${twsPath}" \
  && rm /tmp/ibgw.sh \
  # 关键验证：现在我们验证 jts.jar 是否被解压到了我们的目标路径
  && echo "Verifying that 'jts.jar' was extracted to ${twsPath}..." \
  && ls -R ${twsPath} \
  && test -f "${twsPath}/jars/jts4launch-1030.jar" \
  # 复制 jts.ini 到 IB Gateway 安装目录
  && cp ibc/jts.ini ${twsPath}/jars/jts.ini \
  # 下载并安装 IBC
  && wget -q -O /tmp/IBC.zip https://github.com/IbcAlpha/IBC/releases/download/3.12.0/IBCLinux-3.12.0.zip \
  && unzip /tmp/IBC.zip -d ${ibcPath} \
  && chmod +x ${ibcPath}/*.sh ${ibcPath}/*/*.sh \
  && rm /tmp/IBC.zip

# --- 3. 复制配置文件和脚本 ---
COPY ibc/config.ini ${ibcIni}
# 将 jts.ini 复制到我们的安装根目录

WORKDIR /home
COPY cmd.sh cmd.sh
RUN chmod +x cmd.sh

# --- 4. 最终的 CMD ---
CMD tail -f /dev/null
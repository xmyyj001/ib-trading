FROM python:3.9-slim

# --- 1. 可靠地设置版本和路径 ---
# 使用 ARG 定义版本号，方便未来修改。
ARG TWS_VERSION_ARG=981

# 使用 ENV 设置将在整个镜像中持久存在的环境变量。
# 这是在 Dockerfile 中设置环境变量的正确方法。
ENV TWS_VERSION=${TWS_VERSION_ARG}
ENV TWS_INSTALL_DIR=/root/Jts/ibgateway/${TWS_VERSION}
ENV TWS_INSTALL_LOG=/root/Jts/tws_install.log
ENV ibcIni=/root/ibc/config.ini
ENV ibcPath=/opt/ibc
ENV javaPath=/opt/i4j_jres
# 直接使用 TWS_INSTALL_DIR 来设置 twsPath 和 twsSettingsPath，确保路径一致。
ENV twsPath=${TWS_INSTALL_DIR}
ENV twsSettingsPath=${TWS_INSTALL_DIR}
ENV DISPLAY=:0



# --- 2. 临时修改的调试步骤 ---
RUN apt-get update && apt-get upgrade -y \
  && apt-get install --no-install-recommends -y \
     wget \
     unzip \
     xvfb \
     libxtst6 \
     libxrender1 \
     net-tools \
     openjfx \
  && apt-get clean && apt-get -y autoremove \
  && mkdir -p /tmp ${ibcPath} /root/Jts \
  && wget -q -O /tmp/ibgw.sh https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh \
  && chmod +x /tmp/ibgw.sh \
  && yes n | echo /root/Jts | /tmp/ibgw.sh > ${TWS_INSTALL_LOG} || true \
  && rm /tmp/ibgw.sh \
  # --- 调试命令 ---
  && echo ">>> DEBUG: Listing all contents of /root to find installation path <<<" \
  && ls -lR /root

# # --- 2. 合并和简化安装步骤 ---
# # 将所有依赖安装、IB Gateway 安装、验证和 IBC 安装合并到同一个 RUN 指令中。
# # 这可以减少镜像层数，并确保在一个 shell 会话中完成所有操作，避免变量丢失。
# RUN apt-get update && apt-get upgrade -y \
#   && apt-get install --no-install-recommends -y \
#      wget \
#      unzip \
#      xvfb \
#      libxtst6 \
#      libxrender1 \
#      net-tools \
#      openjfx \
#   && apt-get clean && apt-get -y autoremove \
#   # 创建所有需要的目录
#   && mkdir -p /tmp ${ibcPath} /root/Jts \
#   # 下载并安装 IB Gateway
#   && wget -q -O /tmp/ibgw.sh https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh \
#   && chmod +x /tmp/ibgw.sh \
#   # "yes n" 拒绝启动, "echo" 确认路径, 将日志写入文件, "|| true" 忽略非零退出码
#   && yes n | echo | /tmp/ibgw.sh > ${TWS_INSTALL_LOG} || true \
#   && rm /tmp/ibgw.sh \
#   # 关键的验证步骤：如果此目录不存在，整个构建将失败。
#   && echo "Verifying installation directory: ${TWS_INSTALL_DIR}" \
#   && ls -l ${TWS_INSTALL_DIR} \
#   && echo "Verifying jars directory..." \
#   && ls -l ${TWS_INSTALL_DIR}/jars \
#   # 下载并安装 IBC
#   && wget -q -O /tmp/IBC.zip https://github.com/IbcAlpha/IBC/releases/download/3.12.0/IBCLinux-3.12.0.zip \
#   && unzip /tmp/IBC.zip -d ${ibcPath} \
#   && chmod +x ${ibcPath}/*.sh ${ibcPath}/*/*.sh \
#   && rm /tmp/IBC.zip

# # --- 3. 复制配置文件和脚本 ---
# COPY ibc/config.ini ${ibcIni}
# # 注意：jts.ini 应该放在 /root/Jts 目录下，这是 TWS/IBG 寻找它的地方。
# COPY ibc/jts.ini /root/Jts/jts.ini

# WORKDIR /home
# COPY cmd.sh cmd.sh
# RUN chmod +x cmd.sh

# # --- 4. 最终的 CMD ---
# # 用于在调试时保持容器运行。
# CMD tail -f /dev/null
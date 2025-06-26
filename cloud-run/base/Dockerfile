# ===================================================================
# == FINAL DEFINITIVE VERSION: cloud-run/base/Dockerfile
# ===================================================================
FROM python:3.9-slim

ENV TWS_VERSION=1030
ENV TWS_PATH=/root/ibgateway
ENV IBC_PATH=/opt/ibc
ENV IBC_INI=${IBC_PATH}/config.ini
ENV DISPLAY=:0

# --- 关键修复：安装完整的字体包 xfonts-base ---
RUN set -e && \
    apt-get update && \
    apt-get install --no-install-recommends -y \
        wget \
        unzip \
        xvfb \
        libxtst6 \
        libxrender1 \
        openjdk-17-jre-headless \
        procps \
        xterm \
        xfonts-base && \
    mkdir -p "${TWS_PATH}" "${IBC_PATH}" && \
    wget -q -O /tmp/ibgw.sh https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh && \
    chmod +x /tmp/ibgw.sh && \
    /tmp/ibgw.sh -q -dir "${TWS_PATH}/${TWS_VERSION}" && \
    if [ ! -f "${TWS_PATH}/${TWS_VERSION}/jars/jts4launch-${TWS_VERSION}.jar" ]; then echo "ERROR: Core file not found!" >&2; exit 1; fi && \
    ln -s "${TWS_PATH}/${TWS_VERSION}/jars/jts4launch-${TWS_VERSION}.jar" "${TWS_PATH}/${TWS_VERSION}/jars/jts.jar" && \
    wget -q -O /tmp/IBC.zip https://github.com/IbcAlpha/IBC/releases/download/3.12.0/IBCLinux-3.12.0.zip && \
    unzip -q /tmp/IBC.zip -d "${IBC_PATH}" && \
    chmod +x ${IBC_PATH}/*.sh ${IBC_PATH}/scripts/*.sh && \
    cp "${TWS_PATH}/${TWS_VERSION}/ibgateway.vmoptions" "${IBC_PATH}/ibgateway.vmoptions" && \
    rm -f /tmp/ibgw.sh /tmp/IBC.zip && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY ibc/config.ini ${IBC_INI}
COPY ibc/jts.ini "${TWS_PATH}/${TWS_VERSION}/jts.ini"
# 最终版 application/Dockerfile
# 我们不再使用任何构建参数 (ARG)，直接硬编码最终正确的镜像地址。
# 这能保证无论在何种环境下构建，基础镜像的来源都是唯一的、正确的。
FROM europe-docker.pkg.dev/gold-gearbox-424413-k1/cloud-run-repo/base:latest

# 设置 TWS_PATH 环境变量，这个环境变量会被应用继承
ENV TWS_PATH=/root/ibgateway

# copy Python application and pip install packages
WORKDIR /home
COPY app .
RUN python -m pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# execute cmd script
CMD ["./cmd.sh"]
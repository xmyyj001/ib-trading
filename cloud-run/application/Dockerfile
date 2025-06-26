# ===================================================================
# == FINAL CORRECTED application/Dockerfile
# ===================================================================

# 1. 从正确的、静态的 base 镜像地址开始
ARG BASE_IMAGE_URL=europe-docker.pkg.dev/${PROJECT_ID}/cloud-run-repo/base:latest

FROM ${BASE_IMAGE_URL}

# 2. 设置工作目录
WORKDIR /home/app

# 3. 复制并安装依赖 (包含 gunicorn)
COPY app/requirements.txt .
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 4. 复制应用代码
COPY app/ .

# 5. 复制应用专属的启动脚本
COPY cmd.sh .
RUN chmod +x cmd.sh

# 6. 执行启动脚本
CMD ["./cmd.sh"]
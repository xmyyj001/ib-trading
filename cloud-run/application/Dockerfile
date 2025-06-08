# 定义构建参数，并提供默认值
ARG BASE_IMAGE_TAG=latest
ARG GCP_PROJECT_ID  # 您的项目ID
ARG AR_REPO_NAME=eu.gcr.io # 您的 Artifact Registry 仓库名 (这里是 eu.gcr.io)

# 使用构建参数构建基础镜像的完整路径
FROM europe-docker.pkg.dev/${GCP_PROJECT_ID}/${AR_REPO_NAME}/cloud-run/base:${BASE_IMAGE_TAG}

# copy Python application and pip install packages
WORKDIR /home
COPY app .
RUN python -m pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# execute cmd script
CMD ["./cmd.sh"]
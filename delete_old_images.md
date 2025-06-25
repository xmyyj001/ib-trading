
我们需要删除 `base` 和 `application` 这两个镜像的所有版本，特别是那个被标记为 `latest` 的。

#### 1.1 列出所有镜像版本（可选，用于确认）

您可以先列出 `base` 镜像的所有版本，看看都有哪些：
```bash
gcloud artifacts docker images list europe-docker.pkg.dev/gold-gearbox-424413-k1/cloud-run-repo/base --include-tags
```
再列出 `application` 镜像的所有版本：
```bash
gcloud artifacts docker images list europe-docker.pkg.dev/gold-gearbox-424413-k1/cloud-run-repo/application --include-tags
```

#### 1.2 删除 `base:latest` 镜像

这个命令会删除 `base` 镜像中被标记为 `latest` 的那个版本。

```bash
echo "即将删除基础镜像 'base:latest'..."
gcloud artifacts docker images delete \
  "europe-docker.pkg.dev/gold-gearbox-424413-k1/cloud-run-repo/base:latest" \
  --delete-tags \
  --quiet
echo "基础镜像 'base:latest' 已删除。"
```
*   `--delete-tags`: 同时删除与这个镜像版本关联的所有标签（比如 `latest`）。
*   `--quiet`: 自动回答 `y`，无需手动确认。

#### 1.3 删除 `application` 镜像的所有版本

为了确保干净，我们最好把 `application` 镜像也一并删除。

```bash
echo "即将删除应用镜像 'application:latest'..."
gcloud artifacts docker images delete \
  "europe-docker.pkg.dev/gold-gearbox-424413-k1/cloud-run-repo/application:latest" \
  --delete-tags \
  --quiet
echo "应用镜像 'application:latest' 已删除。"

# 如果您还用 commit SHA 作为标签，也可能需要删除它们，但这步通常不是必须的
# gcloud artifacts docker images delete "europe-docker.pkg.dev/gold-gearbox-424413-k1/cloud-run-repo/application:7bdb6a0" --delete-tags --quiet
```

#### 1.4 删除 镜像的所有版本
```bash
# 删除 'base' 镜像的所有版本

echo "### 正在彻底清理 'base' 镜像... ###"
gcloud artifacts docker images delete \
  "europe-docker.pkg.dev/gold-gearbox-424413-k1/cloud-run-repo/base" \
  --delete-tags --quiet

# 删除 'application' 镜像的所有版本
echo "### 正在彻底清理 'application' 镜像... ###"
gcloud artifacts docker images delete \
  "europe-docker.pkg.dev/gold-gearbox-424413-k1/cloud-run-repo/application" \
  --delete-tags --quiet

echo "### 镜像清理完成！现在仓库是空的。 ###"
```
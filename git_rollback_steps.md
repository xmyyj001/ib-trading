# 本地回退到远程Git仓库历史版本的步骤

## 准备工作
1. 确保没有未提交的更改（否则会被永久丢失）：
   ```bash
   git status
   ```
   如果有未提交更改，先提交或使用`git stash`暂存

2. 获取远程仓库最新信息：
   ```bash
   git fetch origin
   ```

## 确定目标版本
1. 查看远程分支提交历史：
   ```bash
   git log origin/main  # 替换main为你的分支名
   ```
2. 复制目标提交的完整哈希值（如`a1b2c3d...`）

## 执行回退
1. 硬重置到目标提交：
   ```bash
   git reset --hard a1b2c3d  # 替换为实际哈希
   ```
2. 强制推送更新远程仓库（可选，仅当需要远程回退时）：
   ```bash
   git push --force origin main  # 谨慎操作！
   ```

## 验证
```bash
git log -1  # 确认当前提交
git status  # 确认工作区干净
```

## ⚠️ 注意事项
- `--hard`会丢弃所有本地未提交更改
- 强制推送(`--force`)会覆盖远程历史，确保团队协作中不会影响他人
- 建议在重要分支操作前创建备份分支：
  ```bash
  git checkout -b backup-before-rollback

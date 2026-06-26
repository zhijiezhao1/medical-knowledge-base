#!/bin/bash
cd "$(dirname "$0")"

# Railway 持久化存储配置
# Railway 会自动将持久化卷挂载到 /data 目录
export DATA_DIR="/data"
export UPLOAD_DIR="/data/uploads"

# 确保数据目录存在
mkdir -p "$DATA_DIR" "$UPLOAD_DIR"

# 启动后端服务
python3 backend/server.py

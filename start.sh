#!/bin/bash

# 视频下载管理器启动脚本 - Linux版本

# 设置环境变量
export PYTHONPATH=$(pwd):$PYTHONPATH

# 创建必要的目录
mkdir -p logs
mkdir -p db
mkdir -p tools

pip install -r requirements.txt

echo "启动中……"
uvicorn main:app --host 0.0.0.0 --port 8000 --works 1
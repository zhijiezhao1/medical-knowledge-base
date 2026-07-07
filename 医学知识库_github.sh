#!/bin/bash
# GitHub 便捷操作脚本

cd "$(dirname "$0")"

# 设置 PATH
export PATH="$HOME/bin:/usr/local/bin:$PATH"

case "$1" in
    "status")
        gh auth status
        ;;
    "push")
        git push
        ;;
    "pull")
        git pull
        ;;
    "log")
        git log --oneline -10
        ;;
    "sync")
        git fetch && git pull && git push
        ;;
    *)
        echo "用法: $0 {status|push|pull|log|sync}"
        echo "  status - 查看 GitHub 认证状态"
        echo "  push   - 推送到 GitHub"
        echo "  pull   - 从 GitHub 拉取"
        echo "  log    - 查看最近提交"
        echo "  sync   - 同步（拉取+推送）"
        ;;
esac

#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

usage() {
  echo "用法: ./run.sh {dev|up|down|logs|ps|test}"
  echo "  dev   构建并在前台启动，适合本地调试"
  echo "  up    构建并在后台启动"
  echo "  down  停止并删除项目容器"
  echo "  logs  持续查看服务日志"
  echo "  ps    查看服务状态"
  echo "  test  运行后端和前端测试"
}

case "${1:-}" in
  dev)
    docker compose -f compose.dev.yml up --build
    ;;
  up)
    docker compose up --build --detach
    echo "GoPro 多机控制台已启动: http://localhost:${GOPRO_WEB_PORT:-15173}"
    ;;
  down)
    docker compose down
    ;;
  logs)
    docker compose logs --follow
    ;;
  ps)
    docker compose ps
    ;;
  test)
    (
      cd backend
      UV_CACHE_DIR=/tmp/gopro-uv-cache uv run pytest -q
    )
    (
      cd frontend
      npm run test
      npm run build
    )
    ;;
  *)
    usage
    exit 1
    ;;
esac

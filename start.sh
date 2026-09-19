#!/usr/bin/env bash
# =============================================================================
# 连铸生产节奏模拟平台 —— 一键启动脚本
#
# 用法：
#   ./start.sh              构建镜像并以后台方式启动全部服务（db+backend+frontend）
#   ./start.sh up           同上（前台日志，Ctrl+C 停止）
#   ./start.sh stop         停止并移除容器（保留数据卷）
#   ./start.sh down         停止并删除容器与数据卷（清空所有数据）
#   ./start.sh restart      重启服务
#   ./start.sh logs         跟踪全部服务日志
#   ./start.sh test         在一次性容器中运行后端 pytest（不影响运行中的服务）
#   ./start.sh dev-backend  本地模式：仅启动 PostgreSQL，FastAPI 跑在本机 8000
#   ./start.sh dev-frontend 本地模式：npm run dev（需后端已启动）
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"

# 优先使用 docker compose（v2），回退 docker-compose（v1）
if docker compose version >/dev/null 2>&1; then
    DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    DC="docker-compose"
else
    echo "❌ 未检测到 Docker Compose，请先安装 Docker。" >&2
    exit 1
fi

# 首次运行生成 .env
if [[ ! -f .env ]]; then
    cp .env.example .env
    echo "📄 已生成 .env（默认配置，可按需修改）"
fi
# shellcheck disable=SC1091
set -a; source .env; set +a

cmd="${1:-start}"

wait_http() {
    local url=$1 name=$2 tries=${3:-60}
    echo -n "⏳ 等待 ${name} 就绪"
    for ((i=1; i<=tries; i++)); do
        if curl -fsS "$url" >/dev/null 2>&1; then
            echo " ✅"; return 0
        fi
        echo -n "."; sleep 2
    done
    echo " ❌（${url} 超时未就绪，请用 '$0 logs' 查看日志）"; return 1
}

case "$cmd" in
  start)
    $DC up -d --build
    wait_http "http://localhost:${BACKEND_PORT:-8000}/api/health" "FastAPI"
    wait_http "http://localhost:${FRONTEND_PORT:-8080}/" "前端页面"
    cat <<EOF

============================================================
  🎉 连铸生产节奏模拟平台已启动

  📊 前端平台：  http://localhost:${FRONTEND_PORT:-8080}
  🔌 API 文档：  http://localhost:${BACKEND_PORT:-8000}/docs
  ❤️  健康检查：  http://localhost:${BACKEND_PORT:-8000}/api/health
  🗄️  PostgreSQL localhost:${DB_PORT:-5432} （库 ${POSTGRES_DB:-castsim}）

  演示场景已自动写入，可直接在页面右上角选择并运行模拟。

  常用命令：$0 logs | $0 stop | $0 down | $0 test
============================================================
EOF
    ;;

  up)
    $DC up --build
    ;;

  stop)
    $DC stop
    $DC rm -f
    echo "🛑 服务已停止（数据卷保留，重启后数据仍在）"
    ;;

  down)
    $DC down -v
    echo "🧹 容器与数据卷已删除"
    ;;

  restart)
    $DC restart
    wait_http "http://localhost:${BACKEND_PORT:-8000}/api/health" "FastAPI"
    wait_http "http://localhost:${FRONTEND_PORT:-8080}/" "前端页面"
    echo "🔄 已重启：http://localhost:${FRONTEND_PORT:-8080}"
    ;;

  logs)
    $DC logs -f --tail=200
    ;;

  test)
    echo "🧪 在一次性容器中运行后端测试（SQLite，无需外部数据库）..."
    docker build -q -t castsim-backend:test ./backend >/dev/null
    docker run --rm \
        -e DATABASE_URL="sqlite:////tmp/test.db" \
        -e SEED_ON_START=false \
        -w /app \
        castsim-backend:test \
        python -m pytest -v tests/
    echo "🧪 前端构建校验..."
    docker build -q -t castsim-frontend:test ./frontend >/dev/null && echo "✅ 前端构建通过"
    ;;

  dev-backend)
    echo "🗄️  仅启动 PostgreSQL 容器..."
    $DC up -d db
    echo "请在本机另开终端运行："
    echo "  cd backend && python -m venv .venv && source .venv/bin/activate"
    echo "  pip install -r requirements.txt"
    echo "  export DATABASE_URL='postgresql+psycopg2://${POSTGRES_USER:-castsim}:${POSTGRES_PASSWORD:-castsim_pwd}@localhost:${DB_PORT:-5432}/${POSTGRES_DB:-castsim}'"
    echo "  uvicorn app.main:app --reload"
    ;;

  dev-frontend)
    echo "⚡ 启动 Vite 开发服务器（代理 /api -> localhost:${BACKEND_PORT:-8000}）"
    cd frontend
    [[ -d node_modules ]] || npm install
    npm run dev
    ;;

  *)
    echo "未知命令：$cmd"; echo "支持：start | up | stop | down | restart | logs | test | dev-backend | dev-frontend"
    exit 1
    ;;
esac

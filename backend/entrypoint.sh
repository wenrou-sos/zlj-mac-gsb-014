#!/usr/bin/env bash
# 等待 PostgreSQL 就绪 -> 建表 -> 可选写入演示数据 -> 启动 API
set -euo pipefail

MAX_WAIT=${DB_MAX_WAIT:-60}
WAITED=0

if [[ "${DATABASE_URL:-}" == postgresql* ]]; then
    echo "[entrypoint] 等待数据库就绪..."
    until python -c "
import os, sys
from sqlalchemy import create_engine, text
try:
    engine = create_engine(os.environ['DATABASE_URL'])
    with engine.connect() as conn:
        conn.execute(text('SELECT 1'))
except Exception as e:
    sys.exit(1)
" 2>/dev/null; do
        WAITED=$((WAITED + 2))
        if (( WAITED >= MAX_WAIT )); then
            echo "[entrypoint] 数据库等待超时 (${MAX_WAIT}s)" >&2
            exit 1
        fi
        sleep 2
    done
    echo "[entrypoint] 数据库已就绪（等待 ${WAITED}s）"
fi

echo "[entrypoint] 初始化数据表..."
python -c "from app.database import init_db; init_db()"

if [[ "${SEED_ON_START:-true}" == "true" ]]; then
    echo "[entrypoint] 写入演示数据（幂等）..."
    python - <<'PY'
from app.database import SessionLocal, init_db
from app import models  # noqa: F401
from app.main import seed_demo

init_db()
db = SessionLocal()
try:
    seed_demo(db)
    print("[entrypoint] 演示数据已就绪")
finally:
    db.close()
PY
fi

echo "[entrypoint] 启动 FastAPI..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000

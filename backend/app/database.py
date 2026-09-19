"""数据库连接配置。

DATABASE_URL 未设置时回退到本地 SQLite（便于单元测试与无数据库快速启动），
生产/Docker 通过环境变量指向 PostgreSQL。
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL", "sqlite:///./castsim.db"
)

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    # 触发模型注册后再建表
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

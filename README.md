# 🏗️ 连铸生产节奏模拟平台

面向钢铁厂连铸工序的生产节奏（热调试/排程）模拟平台。可配置**钢包到达时间、浇铸周期、铸机能力、设备停机区间**，自动识别**断浇风险**并给出**排程调整建议**（降速拉坯 / 改派铸机 / 调整开浇时间 / 产能分流），并以甘特图直观展示。

技术栈：**Vue 3 + Vite**（前端） · **FastAPI + SQLAlchemy**（后端） · **PostgreSQL**（数据库） · **Docker Compose**（一键部署）。

---

## 一、快速开始（Docker 一键启动）

前置条件：已安装 Docker 20.10+ 与 Docker Compose v2。

```bash
./start.sh
```

脚本会自动：

1. 生成 `.env`（可改端口/数据库密码）；
2. 构建并启动 PostgreSQL、FastAPI、Nginx 三个容器；
3. 等待健康检查通过；
4. 自动写入一套演示排程（两铸机白班计划，含缓冲带炉次与停机冲突炉次）。

启动后访问：

| 服务 | 地址 |
| --- | --- |
| 📊 模拟平台前端 | http://localhost:8080 |
| 🔌 FastAPI 交互文档 | http://localhost:8000/docs |
| ❤️ 健康检查 | http://localhost:8000/api/health |

### 其他脚本命令

```bash
./start.sh stop         # 停止（保留数据）
./start.sh down         # 停止并清空数据卷
./start.sh restart      # 重启
./start.sh logs         # 跟踪日志
./start.sh test         # 容器内运行后端 pytest + 前端构建校验
./start.sh dev-backend  # 只起 PostgreSQL，本机跑后端（热重载）
./start.sh dev-frontend # 本机跑 Vite 开发服务器
```

也可以直接使用 compose：

```bash
docker compose up -d --build
docker compose logs -f backend
```

---

## 二、功能说明

### 可配置项

- **铸机配置**：编号、名称、浇铸周期（min/炉）、降速缓冲（min）、炉数能力、吨位能力。
- **钢包（炉次）计划**：炉次号、到达时间、钢种、单重、**指定铸机（留空 = 系统自动分配）**。
- **设备停机区间**：铸机、起止时间、停机原因。
- 配置保存在 PostgreSQL，支持多场景管理与历史模拟结果回看。

### 风险识别规则（`backend/app/engine.py`）

定义：**空闲时间 = 下一炉到达时刻 − 上一炉浇完时刻**。

| 情形 | 判定 |
| --- | --- |
| 空闲 ≤ 0（钢包早到） | 等待前炉浇完，正常连浇 |
| 0 < 空闲 ≤ 降速缓冲 | **中风险**：需降速拉坯吸收空隙，否则断浇 |
| 空闲 > 降速缓冲 | **高风险**：超出降速能力，断浇 |
| 浇铸窗口与停机区间重叠（浇次中途） | **高风险**：停机冲突，被迫断浇重开 |
| 首炉到达即遇停机 | **中风险**：等待停机结束 |
| 计划炉数/吨位 > 铸机能力 | **高风险**：产能超载，建议分流 |

每条风险都带**自然语言说明 + 可执行建议**（提前调达分钟数、改派目标、压缩停机窗口等）。

### 两种排程模式

- **基准排程**：严格按人工指定铸机、未指定则"最早空闲铸机"贪心分配；只识别风险、不改计划。
- **优化排程**：
  - 自动对缓冲带炉次执行**降速拉坯**保持连浇；
  - 将自动分配炉次**改派**至无冲突、无需降速的铸机（代价分级贪心，人工钉死的炉次尊重工艺约束不改派）；
  - 返回实际执行的调整动作清单（改派前后铸机、放缓分钟数）。

### 结果可视化

- 时间轴**甘特图**：正常连浇 / 降速衔接 / 断浇重开 / 优化改派四种色块 + 停机斜纹区间 + 钢包到达标记；
- KPI 卡片：总炉数、总吨位、断浇次数、高/中风险数、优化动作数；
- 风险清单、调整建议、逐炉明细表（到达/开浇/浇完/等待/空闲/重量/状态）；
- 各铸机利用率、空闲时长、钢包等待合计。

---

## 三、本地开发（不用 Docker）

### 后端

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 方式 A：SQLite（零依赖，默认）
uvicorn app.main:app --reload

# 方式 B：PostgreSQL
export DATABASE_URL="postgresql+psycopg2://castsim:castsim_pwd@localhost:5432/castsim"
uvicorn app.main:app --reload
```

### 前端

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173，/api 自动代理到 8000
```

### 运行测试

```bash
cd backend
pytest -q          # 26 个测试：引擎规则 + API 端到端
cd ../frontend
npm run build      # 构建校验
```

---

## 四、主要 API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| GET/POST | `/api/scenarios` | 场景列表 / 创建场景 |
| GET | `/api/scenarios/{id}` | 场景完整配置 |
| PUT | `/api/scenarios/{id}/config` | 覆盖式保存铸机/钢包/停机配置 |
| DELETE | `/api/scenarios/{id}` | 删除场景 |
| POST | `/api/scenarios/{id}/simulate?mode=baseline\|optimized` | 执行模拟并存历史 |
| GET | `/api/scenarios/{id}/runs` | 历史模拟结果 |
| POST | `/api/simulate` | 即席模拟（不入库，前端试算） |
| POST | `/api/seed` | 写入演示数据（幂等） |

完整字段见 http://localhost:8000/docs 。

### 即席模拟示例

```bash
curl -X POST http://localhost:8000/api/simulate -H 'Content-Type: application/json' -d '{
  "mode": "optimized",
  "casters": [
    {"code": "CC1", "name": "1#连铸机", "cycle_minutes": 45, "hold_tolerance_minutes": 15},
    {"code": "CC2", "name": "2#连铸机", "cycle_minutes": 50, "hold_tolerance_minutes": 10}
  ],
  "ladles": [
    {"seq": 1, "arrival": "2026-09-18T08:00", "caster_code": "CC1"},
    {"seq": 2, "arrival": "2026-09-18T08:55", "caster_code": "CC1"}
  ],
  "downtimes": []
}'
```

---

## 五、目录结构

```
.
├── start.sh                 # 一键启动脚本
├── docker-compose.yml       # db + backend + frontend 编排
├── .env.example             # 环境变量模板
├── backend/
│   ├── Dockerfile
│   ├── entrypoint.sh        # 等待 DB -> 建表 -> 种子数据 -> 启动
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py          # FastAPI 路由
│   │   ├── engine.py        # 排程模拟 / 风险识别 / 优化器（核心）
│   │   ├── service.py       # ORM -> 引擎入参
│   │   ├── models.py        # SQLAlchemy 模型
│   │   ├── schemas.py       # Pydantic 模型
│   │   └── database.py      # 引擎/Session（支持 PG 与 SQLite 回退）
│   └── tests/               # pytest：引擎规则 18 例 + API 8 例
└── frontend/
    ├── Dockerfile           # 多阶段构建 + nginx 反代
    ├── nginx.conf
    └── src/
        ├── App.vue          # 场景管理 / 布局 / 交互编排
        ├── api.js
        └── components/
            ├── ConfigEditor.vue   # 铸机/钢包/停机配置表格
            ├── GanttChart.vue     # SVG 时间轴甘特图
            ├── RiskPanel.vue      # 断浇风险与建议
            └── AdjustmentPanel.vue
```

## 六、简化假设（可按需扩展）

- 浇铸周期按铸机固定；不区分钢种/断面差异（可在 `CasterSpec` 与炉次匹配规则中扩展）；
- 所有自动分配炉次可在任一铸机浇铸（实际生产存在工艺相容性约束，可扩展为炉-机兼容矩阵）；
- 降速缓冲为单一时间参数，不建模拉速曲线；
- 不模拟精炼/转炉侧节奏，钢包到达时间为外部给定输入。

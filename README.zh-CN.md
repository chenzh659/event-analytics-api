<p align="center">
  <img src="docs/assets/banner.svg" alt="Event Analytics API 横幅" width="100%"/>
</p>

<h1 align="center">event-analytics-api</h1>

<p align="center">
  <strong>用户行为采集与实时指标后端</strong><br/>
  <em>作品集级 FastAPI 服务 — 异步埋点、可靠消息流、指标任务、真实压测数字</em>
</p>

<p align="center">
  <a href="README.md"><img src="https://img.shields.io/badge/lang-English-blue?style=for-the-badge" alt="English"/></a>
  <a href="README.zh-CN.md"><img src="https://img.shields.io/badge/lang-%E4%B8%AD%E6%96%87-red?style=for-the-badge" alt="中文"/></a>
</p>

<p align="center">
  <a href="https://github.com/chenzh659/event-analytics-api/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/chenzh659/event-analytics-api/ci.yml?branch=main&style=for-the-badge&label=CI" alt="CI"/></a>
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI"/>
  <img src="https://img.shields.io/badge/PostgreSQL-17-4169E1?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL"/>
  <img src="https://img.shields.io/badge/Redis-7%20Streams-DC382D?style=for-the-badge&logo=redis&logoColor=white" alt="Redis"/>
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="MIT"/>
</p>

<p align="center">
  <a href="#-功能特性">功能特性</a> ·
  <a href="#-系统架构">系统架构</a> ·
  <a href="#-快速开始">快速开始</a> ·
  <a href="#-api-一览">API</a> ·
  <a href="#-测试与压测">测试与压测</a> ·
  <a href="#-项目结构">项目结构</a> ·
  <a href="#-设计亮点">设计亮点</a> ·
  <a href="docs/resume-talk-track.md">面试话术</a>
</p>

---

## ✨ 功能特性

| 方向 | 能力 |
|------|------|
| **行为埋点** | `view` / `search` / `add_to_cart` / `order` · 单条 + 批量 · API 版本 `/api/v1` |
| **鉴权与 RBAC** | JWT (HS256) · 角色 `admin` / `analyst` / `client_app` · 权限校验 |
| **幂等写入** | 客户端 `event_id` + Redis `SET NX` + DB `UNIQUE` + `ON CONFLICT DO NOTHING` |
| **异步管道** | Redis Streams → ARQ Worker · 可用 `INGEST_MODE` 切同步写库 |
| **可靠消费** | **XAUTOCLAIM** 回收卡住消息 · **DLQ** 毒消息隔离 · Streams `MAXLEN` |
| **指标任务** | 日活 DAU · 漏斗 · D1/D7 留存 · 事务 advisory lock · Redis 缓存旁路 |
| **近似实时 DAU** | 写入路径 HyperLogLog（固定内存、O(1)） |
| **限流** | 滑动窗口 · Lua + ZSET · IP / 用户 / 写事件三级配额 |
| **可观测** | structlog JSON · `X-Request-ID` · Prometheus · Grafana · 路径标签归一化 |
| **健康探针** | `/health` 存活 · `/ready` 就绪（依赖不可用时 **503**） |
| **数据层** | SQLAlchemy 2 async · Alembic · **BRIN(server_ts)** · 部分索引 |
| **工程加固** | 用户乐观锁 · 请求体大小限制 · 安全响应头 |
| **诚信压测** | Locust → CSV → `write_perf_report.py` · **禁止编造 p95 / RPS** |

---

## 🏗 系统架构

<p align="center">
  <img src="docs/assets/architecture.svg" alt="系统架构图" width="100%"/>
</p>

### 可靠接入链路

<p align="center">
  <img src="docs/assets/pipeline.svg" alt="可靠事件管道" width="100%"/>
</p>

<details>
<summary><strong>文字版架构图（便于复制）</strong></summary>

```text
客户端 / Locust
    │  JWT + RBAC + 滑动窗口限流
    ▼
FastAPI  ──SET NX──► Redis 幂等键
    │ XADD（异步）/ INSERT（同步）
    ▼
stream:events  ──►  ARQ Worker
    │                 ├─ XREADGROUP
    │                 ├─ XAUTOCLAIM（回收 PEL）
    │                 ├─ INSERT ON CONFLICT DO NOTHING
    │                 ├─ PFADD hll:dau
    │                 └─ 毒消息 → stream:events:dlq
    ▼
PostgreSQL（events / metrics_* / users）
    ▲
Metrics API ◄── Redis 缓存旁路
Prometheus  ◄── /metrics ──► Grafana
```

</details>

更多细节见：[docs/architecture.md](docs/architecture.md)（英文）

---

## 🚀 快速开始

### 前置条件

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) / Docker Compose v2  
- （可选）本机 Python 3.12，仅用于本地工具脚本  

### 一键启动

```bash
git clone https://github.com/chenzh659/event-analytics-api.git
cd event-analytics-api

cp .env.example .env          # Windows: copy .env.example .env
docker compose up -d --build
```

等待 `api` 变为 healthy：

```bash
curl http://localhost:8001/health
# {"status":"ok","service":"event-analytics-api","version":"1.0.0"}
```

| 入口 | 地址 |
|------|------|
| Swagger 文档 | http://localhost:8001/docs |
| ReDoc | http://localhost:8001/redoc |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3001（`admin` / `admin`） |

> **宿主机端口映射**（避免与其它本地项目冲突）：API **8001**，Postgres **5433**，Redis **6380**，Grafana **3001**。

### 种子账号

| 角色 | Email | Password |
|------|-------|----------|
| admin | `admin@example.com` | `Admin123!` |
| analyst | `analyst@example.com` | `Analyst123!` |
| client_app | `client@example.com` | `Client123!` |

---

## 🎬 约 15 分钟演示

```bash
# 1) client 登录
TOKEN=$(curl -s -X POST http://localhost:8001/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"client@example.com","password":"Client123!"}' | jq -r .access_token)

# 2) 上报事件
EVENT_ID=$(python -c "import uuid; print(uuid.uuid4())")
curl -s -X POST http://localhost:8001/api/v1/events \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"event_id\":\"$EVENT_ID\",\"session_id\":\"demo-1\",\"event_type\":\"view\",\"properties\":{\"page\":\"/home\"}}"

# 3) 幂等重放 → deduplicated: true
curl -s -X POST http://localhost:8001/api/v1/events \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"event_id\":\"$EVENT_ID\",\"session_id\":\"demo-1\",\"event_type\":\"view\",\"properties\":{\"page\":\"/home\"}}"

# 4) 查看 worker 消费日志
docker compose logs worker --tail=50

# 5) 分析师读指标
ANALYST=$(curl -s -X POST http://localhost:8001/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"analyst@example.com","password":"Analyst123!"}' | jq -r .access_token)

curl -s http://localhost:8001/api/v1/metrics/dau -H "Authorization: Bearer $ANALYST"
curl -s http://localhost:8001/api/v1/metrics/funnel -H "Authorization: Bearer $ANALYST"

# 6) 管理员看队列（含 dlq_length）
ADMIN=$(curl -s -X POST http://localhost:8001/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"Admin123!"}' | jq -r .access_token)
curl -s http://localhost:8001/api/v1/admin/queue -H "Authorization: Bearer $ADMIN"
```

Windows PowerShell 可用 `Invoke-RestMethod` 代替 `curl` / `jq`。

---

## 📡 API 一览

| 方法 | 路径 | 权限 |
|------|------|------|
| `POST` | `/api/v1/auth/register` | 公开 |
| `POST` | `/api/v1/auth/login` | 公开 |
| `GET` | `/api/v1/auth/me` | 已登录 |
| `POST` | `/api/v1/events` | `events:write` |
| `POST` | `/api/v1/events/batch` | `events:batch` |
| `GET` | `/api/v1/events/{event_id}` | `events:read` |
| `GET` | `/api/v1/metrics/dau` | `metrics:read` |
| `GET` | `/api/v1/metrics/funnel` | `metrics:read` |
| `GET` | `/api/v1/metrics/retention` | `metrics:read` |
| `GET` | `/api/v1/metrics/realtime/events-per-minute` | `metrics:read` |
| `GET` | `/api/v1/metrics/summary` | `metrics:read` |
| `GET` | `/api/v1/admin/users` | `users:manage` |
| `PATCH` | `/api/v1/admin/users/{id}` | `users:manage`（乐观锁 `version`） |
| `GET` | `/api/v1/admin/queue` | `queue:read` |
| `POST` | `/api/v1/admin/jobs/{job_name}` | `jobs:trigger` |
| `GET` | `/health` · `/ready` · `/metrics` | 公开 / 运维 |

**统一错误体**

```json
{
  "error": {
    "code": "forbidden",
    "message": "Missing permission: metrics:read",
    "request_id": "…"
  }
}
```

交互式文档：启动后打开 **http://localhost:8001/docs**。

---

## ⚙️ 配置要点

详见 [`.env.example`](.env.example)。常用项：

| 变量 | 含义 |
|------|------|
| `INGEST_MODE` | `async`（进 Streams）或 `sync`（请求内写库） |
| `RATE_LIMIT_*` | 滑动窗口配额（IP / 用户 / 写事件） |
| `EVENT_CLAIM_MIN_IDLE_MS` | PEL 空闲多久触发 `XAUTOCLAIM` |
| `EVENT_MAX_DELIVERIES` | 超过次数进 DLQ |
| `CACHE_TTL_*` | 指标缓存 TTL |
| `JWT_SECRET` | **共享环境务必更换** |

---

## 🧪 测试与压测

```bash
# 单元 + ASGI 健康检查
docker compose exec api pytest tests/unit tests/integration/test_health.py -q

# 对运行中栈做 HTTP 集成（容器网络内）
docker compose exec -e RUN_INTEGRATION=1 -e API_BASE_URL=http://api:8000 api \
  pytest tests/integration/test_api_flow.py -q
```

### 性能报告（只认实测数字）

```bash
mkdir -p results

# 示例：50 并发用户，跑 5 分钟（按机器调整）
docker compose exec api locust -f tests/load/locustfile.py \
  --host http://api:8000 \
  --headless -u 50 -r 10 -t 5m --csv=results/run1

docker compose exec api python scripts/write_perf_report.py \
  --csv results/run1_stats.csv \
  --users 50 \
  --duration 5m \
  --out docs/performance-report.md
```

报告模板：[docs/performance-report.md](docs/performance-report.md)（未跑 Locust 前为 TBD）。

可选历史数据（方便演示漏斗 / 留存）：

```bash
docker compose exec api python -m scripts.generate_load_data \
  --days 14 --users 200 --events-per-day 500
```

慢查询辅助（`pg_stat_statements`）：

```bash
docker compose exec -T postgres psql -U events -d events < scripts/analyze_slow_queries.sql
```

---

## 📁 项目结构

```text
event-analytics-api/
├── app/
│   ├── api/v1/           # 版本化路由（auth / events / metrics / admin）
│   ├── core/             # 安全、RBAC、异常、限流、中间件
│   ├── db/models/        # ORM 模型
│   ├── services/         # 业务逻辑
│   ├── mq/               # Redis Streams（生产 / 回收 / DLQ）
│   ├── workers/          # ARQ 配置与任务
│   └── observability/    # Prometheus 指标
├── alembic/              # 迁移（含 BRIN）
├── scripts/              # seed、造数、压测报告、入口脚本
├── tests/                # unit · integration · load (Locust)
├── monitoring/           # Prometheus + Grafana 配置
├── docs/
│   ├── assets/           # README 架构图（SVG）
│   ├── architecture.md
│   ├── performance-report.md
│   └── resume-talk-track.md   # 简历 / 面试中文话术
├── docker-compose.yml
├── README.md             # English
├── README.zh-CN.md       # 中文（本文件）
└── .github/workflows/ci.yml
```

---

## 💡 设计亮点

1. **多层幂等**：客户端 UUID + Redis NX + DB 唯一约束 + 冲突忽略写入。  
2. **写路径解耦**：接口快速返回 **202**，Worker 批量落库，削峰填谷。  
3. **消息可靠**：`XAUTOCLAIM` 回收 PEL；超过投递次数进入 **DLQ**（`stream:events:dlq`）。  
4. **滑动窗口限流**：Redis Lua 原子脚本，边界突发小于固定窗口。  
5. **指标任务**：advisory lock 防并发重算；快照表 + cache-aside；可选 HLL。  
6. **时序索引**：**BRIN(server_ts)** + 部分索引，适合范围扫描。  
7. **乐观锁**：`PATCH /admin/users` 带 `version`，冲突返回 **409**。  
8. **指标基数安全**：Prometheus 标签前将 path 中 UUID 归一为 `{id}`。  
9. **探针分离**：liveness 不查依赖；readiness 查 DB/Redis。  
10. **诚信压测**：报告生成器只接受 Locust 实测 CSV。  

简历 bullet 与面试深挖问答：[docs/resume-talk-track.md](docs/resume-talk-track.md)

---

## 🛠 技术栈

| 层 | 选型 |
|----|------|
| API | Python 3.12 · FastAPI · Uvicorn |
| 数据库 | PostgreSQL · SQLAlchemy 2 async · Alembic · asyncpg |
| 缓存 / 消息 / 任务 | Redis 7 Streams · ARQ |
| 鉴权 | JWT HS256 · bcrypt · RBAC |
| 可观测 | structlog · prometheus-client · Grafana |
| 压测 | Locust |
| 交付 | Docker Compose · GitHub Actions CI |

---

## 🗺 可选演进（Roadmap）

- [ ] 多 Consumer 水平扩展演示  
- [ ] OpenTelemetry 链路追踪  
- [ ] `events` 表按时间分区，支撑更长保留期  
- [ ] CI 友好的短时压测任务 + 自动写报告  

---

## 📄 许可证

[MIT](LICENSE) © 2026 [chenzh659](https://github.com/chenzh659)

---

<p align="center">
  <sub>作品集后端项目 — 生产级模式、诚实的性能数字、面试可讲的设计取舍。</sub>
</p>

# event-analytics-api

用户行为采集与实时指标后端服务（Portfolio / 简历向）。

实现埋点事件接入、JWT + RBAC、幂等写入、Redis Streams 异步管道、日活 / 漏斗 / 留存后台计算、限流、结构化日志、Prometheus / Grafana 监控，以及 **基于真实 Locust 压测结果的性能报告**（禁止编造数字）。

## 技术栈

| 层 | 选型 |
|----|------|
| API | Python 3.12 · FastAPI · Uvicorn |
| DB | PostgreSQL 16 · SQLAlchemy 2 async · Alembic |
| Cache / MQ / Jobs | Redis 7 Streams · ARQ |
| Auth | JWT (HS256) · bcrypt · RBAC |
| Observability | structlog · prometheus-client · Grafana |
| Load test | Locust |

## 架构一览

```
Client/Locust → FastAPI (/api/v1)
                  ├─ POST /events → Redis NX 幂等 → XADD stream:events → 202
                  └─ GET  /metrics → Redis 缓存 → metrics_* 表

stream:events → ARQ worker → PostgreSQL (ON CONFLICT DO NOTHING)
ARQ cron      → DAU / funnel / retention
Prometheus    → scrape /metrics → Grafana :3000
```

详见 [docs/architecture.md](docs/architecture.md)。


## 本地端口映射（避免与其它项目冲突）

| 服务 | 容器端口 | 宿主机 |
|------|----------|--------|
| API | 8000 | **8001** |
| Postgres | 5432 | **5433** |
| Redis | 6379 | **6380** |
| Prometheus | 9090 | 9090 |
| Grafana | 3000 | **3001** |

## 快速启动

### 前置条件

- Docker Desktop / Docker Compose
- （可选）本机 Python 3.12，仅用于本地开发

### 一键启动

```bash
# 在仓库根目录
cp .env.example .env   # Windows: copy .env.example .env

docker compose up -d --build
```

等待 `api` healthy 后：

```bash
curl http://localhost:8001/health
# {"status":"ok","service":"event-analytics-api","version":"1.0.0"}
```

- API 文档：http://localhost:8001/docs  
- Prometheus：http://localhost:9090  
- Grafana：http://localhost:3001（宿主机端口映射，避免与其它项目冲突） （`admin` / `admin`）

### 种子账号

| 角色 | Email | Password |
|------|-------|----------|
| admin | admin@example.com | Admin123! |
| analyst | analyst@example.com | Analyst123! |
| client_app | client@example.com | Client123! |

## 演示流程（约 15 分钟）

```bash
# 1. 登录 client
TOKEN=$(curl -s -X POST http://localhost:8001/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"client@example.com","password":"Client123!"}' | jq -r .access_token)

# 2. 上报事件
EVENT_ID=$(python -c "import uuid; print(uuid.uuid4())")
curl -s -X POST http://localhost:8001/api/v1/events \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"event_id\":\"$EVENT_ID\",\"session_id\":\"demo-1\",\"event_type\":\"view\",\"properties\":{\"page\":\"/home\"}}"

# 3. 幂等重放（应返回 deduplicated: true）
curl -s -X POST http://localhost:8001/api/v1/events \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"event_id\":\"$EVENT_ID\",\"session_id\":\"demo-1\",\"event_type\":\"view\",\"properties\":{\"page\":\"/home\"}}"

# 4. 查看 worker 消费
docker compose logs worker --tail=50

# 5. 分析师读指标
ANALYST=$(curl -s -X POST http://localhost:8001/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"analyst@example.com","password":"Analyst123!"}' | jq -r .access_token)

curl -s http://localhost:8001/api/v1/metrics/dau -H "Authorization: Bearer $ANALYST"
curl -s http://localhost:8001/api/v1/metrics/funnel -H "Authorization: Bearer $ANALYST"
curl -s http://localhost:8001/metrics | head
```

Windows PowerShell 可用 `Invoke-RestMethod` 代替 `curl` / `jq`。

## 主要 API（v1）

| 方法 | 路径 | 权限 |
|------|------|------|
| POST | `/api/v1/auth/register` | public |
| POST | `/api/v1/auth/login` | public |
| GET | `/api/v1/auth/me` | authenticated |
| POST | `/api/v1/events` | `events:write` |
| POST | `/api/v1/events/batch` | `events:batch` |
| GET | `/api/v1/events/{event_id}` | `events:read` |
| GET | `/api/v1/metrics/dau` | `metrics:read` |
| GET | `/api/v1/metrics/funnel` | `metrics:read` |
| GET | `/api/v1/metrics/retention` | `metrics:read` |
| GET | `/api/v1/metrics/realtime/events-per-minute` | `metrics:read` |
| GET | `/api/v1/metrics/summary` | `metrics:read` |
| GET | `/api/v1/admin/users` | `users:manage` |
| PATCH | `/api/v1/admin/users/{id}` | `users:manage`（乐观锁 `version`） |
| GET | `/api/v1/admin/queue` | `queue:read` |
| POST | `/api/v1/admin/jobs/{job_name}` | `jobs:trigger` |
| GET | `/health` · `/ready` · `/metrics` | public / ops |

统一错误体：

```json
{ "error": { "code": "forbidden", "message": "...", "request_id": "..." } }
```

## 配置要点

见 [`.env.example`](.env.example)。

- `INGEST_MODE=async|sync`：异步进 Streams，或同步写库  
- 限流：`RATE_LIMIT_IP` / `RATE_LIMIT_USER` / `RATE_LIMIT_EVENTS`  
- 缓存 TTL：`CACHE_TTL_*`  

## 测试

```bash
# 单元 + ASGI smoke（不强制外部依赖）
docker compose exec api pytest tests/unit tests/integration/test_health.py -q

# 全链路集成（容器内）
docker compose exec -e RUN_INTEGRATION=1 api pytest tests/integration -q --cov=app
```

## 压测与性能报告（真实数字）

**禁止手写 p95 / RPS。** 用脚本从 Locust CSV 生成：

```bash
mkdir -p results

# 示例：50 并发用户，跑 5 分钟
docker compose exec api locust -f tests/load/locustfile.py \
  --host http://localhost:8001 \
  --headless -u 50 -r 10 -t 5m --csv=results/run1

docker compose exec api pytest -q --cov=app --cov-report=term-missing

docker compose exec api python scripts/write_perf_report.py \
  --csv results/run1_stats.csv \
  --users 50 \
  --duration 5m \
  --out docs/performance-report.md
```

报告模板与说明：[docs/performance-report.md](docs/performance-report.md)

可选历史数据（便于漏斗 / 留存）：

```bash
docker compose exec api python -m scripts.generate_load_data \
  --days 14 --users 200 --events-per-day 500
```

慢查询分析：

```bash
docker compose exec -T postgres psql -U events -d events < scripts/analyze_slow_queries.sql
```

## 项目结构

```
app/
  api/v1/          # 路由
  core/            # 安全、RBAC、异常、限流、中间件
  db/models/       # ORM
  services/        # 业务
  mq/              # Redis Streams
  workers/         # ARQ
  observability/   # Prometheus 指标
scripts/           # seed / 压测报告 / 慢查询
tests/             # unit · integration · load
monitoring/        # Prometheus & Grafana
docs/              # 架构与性能报告
```

## 设计说明（简历可讲点）

1. **幂等**：客户端 `event_id` + Redis `SET NX` + DB `UNIQUE` + `ON CONFLICT DO NOTHING`，兼容 at-least-once。  
2. **异步解耦**：接入路径快速返回 202，worker 批量落库；Streams **MAXLEN** 控内存。  
3. **可靠消费**：`XAUTOCLAIM` 回收 PEL 卡住消息；超过投递次数进 **DLQ**（`stream:events:dlq`）。  
4. **滑动窗口限流**：Redis ZSET + Lua 原子脚本，按 IP / 用户 / 写事件三级配额。  
5. **指标任务**：advisory lock 防并发重算；快照表 + cache-aside；**HyperLogLog** 近似实时 DAU。  
6. **存储**：时序场景 **BRIN(server_ts)** + 部分索引；`pg_stat_statements` 慢查询脚本。  
7. **乐观锁**：`PATCH /admin/users` 要求 `version`，冲突 409。  
8. **可观测**：`X-Request-ID`、路径归一化 Prometheus 标签、liveness/readiness 分离、Grafana 面板。  
9. **诚信压测**：报告只由 `write_perf_report.py` 从 Locust CSV 写出。  

面试话术与 bullet 模板见：[docs/resume-talk-track.md](docs/resume-talk-track.md)。

## License

MIT（可按需修改）

# 简历亮点与面试话术（event-analytics-api）

> 写简历时挑 3～5 条最有数字/最有决策的写；面试按「场景 → 方案 → 权衡 → 结果」讲。

## 一句话定位

**用户行为采集与实时指标后端**：异步埋点接入、幂等去重、Redis Streams 可靠消费、日活/漏斗/留存离线计算、限流与可观测，配套真实压测报告（禁止编造数字）。

---

## 简历 bullet 示例（可直接改数字）

1. 设计并实现 **异步埋点管道**（FastAPI → Redis Streams → ARQ Worker → PostgreSQL），接入路径返回 202，削峰填谷，与同步写库模式可配置切换。  
2. 实现 **多层幂等**：客户端 `event_id` + Redis `SET NX` + DB `UNIQUE` + `ON CONFLICT DO NOTHING`，兼容 at-least-once 投递，重复上报不双计。  
3. 参考大厂消息队列实践，实现 **XAUTOCLAIM 回收 PEL 卡住消息** + **毒消息死信队列（DLQ）** + 投递次数上限，避免无限重试打爆下游。  
4. 指标侧：**DAU / 漏斗 / 留存** 定时任务 + `pg_advisory_xact_lock` 防并发重算；Redis cache-aside；**HyperLogLog** 维护近似实时 DAU（O(1) 内存）。  
5. 限流采用 **滑动窗口 + Redis Lua 原子脚本**（相对固定窗口减少边界突发），按 IP / 用户 / 写事件三级配额。  
6. 可观测：结构化日志 + `X-Request-ID`；Prometheus 指标 **路径归一化**（UUID→`{id}`）控制基数；`/health` 与 `/ready` 分离（liveness / readiness）。  
7. 存储优化：事件表 **BRIN(server_ts)** + 部分索引，面向时序范围扫描；预留 `pg_stat_statements` 慢查询分析脚本。  
8. 管理端用户更新使用 **乐观锁 version**，冲突返回 409，避免丢失更新。  
9. 压测链路：Locust → CSV → `write_perf_report.py` 自动生成报告，**报告数字仅来自实测**。

---

## 面试深挖：你可以怎么答

### 1. 为什么用 Redis Streams 而不是 Kafka？

| | Redis Streams | Kafka |
|--|---------------|-------|
| 运维 | 与缓存/限流共用 Redis，Compose 一键 | 需 ZK/KRaft、多 broker |
| 语义 | Consumer Group + PEL + ACK | 分区消费 + offset |
| 适合规模 | 中小流量埋点、作品集/中台 | 超大吞吐、多机房 |

**话术**：作品集场景优先 **可控复杂度**；Streams 已具备「组消费 + 未确认列表 + 认领」核心语义，足够演示可靠投递。上线到日亿级再评估 Kafka/Pulsar。

### 2. 幂等如何保证？

1. 客户端生成 UUID `event_id`  
2. API：`SET idem:{id} NX` 抢占  
3. 异步：`XADD`；Worker：`INSERT … ON CONFLICT DO NOTHING`  
4. 重放：Redis 已有 key → 直接 `deduplicated: true`  
5. 最终以 DB 唯一约束为准（Redis 丢失也不双写）

### 3. 卡住的消息怎么办？（体现可靠性）

- 处理失败 **不 ACK** → 留在 PEL  
- 定时 **XAUTOCLAIM** 认领 idle > 60s 的消息  
- `delivery_count >= max` → 写入 **DLQ stream** 并 ACK 原消息  
- 运维可查 `GET /admin/queue` 的 `pending` / `dlq_length`

### 4. 固定窗口 vs 滑动窗口限流？

固定窗口在窗口边界可出现约 **2 倍突发**；滑动窗口用 ZSET 记录时间戳，Lua 内 `ZREMRANGEBYSCORE + ZCARD + ZADD` **单原子**，更贴近网关行为。

### 5. DAU 精确 vs 近似？

| | 精确 COUNT DISTINCT | HyperLogLog |
|--|---------------------|-------------|
| 误差 | 0 | ~0.81% 标准误差 |
| 成本 | 随数据量变贵 | 固定约 12KB/key |
| 用途 | 日报/对账（本项目默认） | 实时大盘/告警 |

### 6. 为什么 Prometheus 不能直接用原始 path？

`/events/{uuid}` 每个 UUID 一个 label → **基数爆炸** 打挂 TSDB。中间件把 UUID/数字归一成 `{id}`。

### 7. health vs ready？

- **liveness `/health`**：进程活着即可，不查依赖（避免依赖抖动导致杀进程重启风暴）  
- **readiness `/ready`**：DB/Redis 不通返回 **503**，从负载均衡摘除

---

## 架构一句话（白板）

```
Client → API(JWT/RBAC/RL/Idem) → Streams → Worker(XAUTOCLAIM/DLQ) → PG
                                  ↘ Redis cache / HLL / sliding RL
Cron → DAU/Funnel/Retention snapshots → Metrics API
Prometheus ← /metrics  Grafana
```

---

## 演示顺序（15 分钟）

1. `docker compose up -d` + `/health` `/docs`  
2. 登录 client → 上报 → 重放幂等  
3. worker 日志插入 + `admin/queue`  
4. analyst 看 DAU/funnel  
5. 故意用 client 调 metrics → 403  
6. admin 改用户 version 冲突 → 409  
7. Grafana / Prometheus 看 QPS、lag  
8. （可选）Locust + 生成 performance-report  

---

## 诚实边界（面试加分）

- 性能报告 **未跑则写 TBD**，跑完用脚本生成  
- 单机 Compose，不是多机房；Streams 非跨机房强一致  
- HLL 是近似，**对账以 SQL COUNT DISTINCT 为准**

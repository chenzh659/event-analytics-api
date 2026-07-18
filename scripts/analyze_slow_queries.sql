-- Slow query analysis helpers (requires pg_stat_statements).
-- Usage:
--   docker compose exec postgres psql -U events -d events -f /path/or/paste

-- Top statements by total time
SELECT
  substring(query, 1, 120) AS query_preview,
  calls,
  round(total_exec_time::numeric, 2) AS total_ms,
  round(mean_exec_time::numeric, 2) AS mean_ms,
  rows
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;

-- Event table indexes
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'events';

-- Example EXPLAIN for DAU-style query (replace timestamps)
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(DISTINCT user_id)
FROM events
WHERE server_ts >= NOW() - INTERVAL '1 day'
  AND user_id IS NOT NULL;

-- Import each SELECT as a separate Power Query query named in the preceding comment.
-- No USE/GO in the SQL Server connector's SQL statement box. Database: DataWarehouse.

-- audit_families: one root per family; includes standalone roots for honest history.
SELECT CONVERT(varchar(36),run_id) AS family_id,component AS root_component,
 status AS root_status,started_at_utc AS root_started_at_utc
FROM audit.pipeline_runs WHERE parent_run_id IS NULL;
GO
-- audit_runs: one row per run. Deliberately excludes error/summary free text.
SELECT CONVERT(varchar(36),run_id) AS run_id,
 CONVERT(varchar(36),COALESCE(parent_run_id,run_id)) AS family_id,
 component,mode,status,started_at_utc,ended_at_utc,failure_stage,
 DATEDIFF_BIG(millisecond,started_at_utc,ended_at_utc)/1000.0 AS elapsed_seconds
FROM audit.pipeline_runs;
GO
-- audit_steps: one row per (run_id,ordinal).
SELECT CONVERT(varchar(36),run_id) AS run_id,ordinal,name,status,
 started_at_utc,ended_at_utc,duration_seconds FROM audit.pipeline_steps;
GO
-- audit_quality: one row per (run_id,check_id); mart details are NOT stored here.
SELECT CONVERT(varchar(36),run_id) AS run_id,check_id,severity,status,anomaly_count,metric_value,
 duration_seconds FROM audit.quality_results;
GO
-- audit_snapshot: one disconnected row. No assumed exact COMMIT time or all-writer coverage.
SELECT SYSUTCDATETIME() AS observed_at_utc,
 m.ended_at_utc AS last_confirmed_mart_completion_utc,
 e.ended_at_utc AS last_successful_e2e_utc,e.elapsed_seconds AS last_successful_e2e_seconds,
 a.status AS latest_e2e_status,a.started_at_utc AS latest_e2e_started_utc,
 CONVERT(varchar(36),a.run_id) AS latest_e2e_run_id
FROM (SELECT 1 AS anchor) seed
OUTER APPLY (SELECT TOP(1) ended_at_utc FROM audit.pipeline_runs
 WHERE component='mart' AND mode='execute' AND status='PASS'
 ORDER BY ended_at_utc DESC,run_id DESC) m
OUTER APPLY (SELECT TOP(1) ended_at_utc,
 DATEDIFF_BIG(millisecond,started_at_utc,ended_at_utc)/1000.0 AS elapsed_seconds
 FROM audit.pipeline_runs WHERE component='e2e' AND mode='execute' AND status='PASS'
 ORDER BY ended_at_utc DESC,run_id DESC) e
OUTER APPLY (SELECT TOP(1) run_id,status,started_at_utc FROM audit.pipeline_runs
 WHERE component='e2e' ORDER BY started_at_utc DESC,run_id DESC) a;

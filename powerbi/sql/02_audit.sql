USE DataWarehouse;
GO
-- Latest attempt, not only latest success; don't hide a more recent failure.
DECLARE @parent uniqueidentifier=(SELECT TOP(1) run_id FROM audit.pipeline_runs
 WHERE component='e2e' ORDER BY started_at_utc DESC,run_id DESC);
SELECT run_id,parent_run_id,component,mode,status,started_at_utc,ended_at_utc,failure_stage,
 DATEDIFF_BIG(millisecond,started_at_utc,ended_at_utc)/1000.0 AS elapsed_seconds
FROM audit.pipeline_runs WHERE run_id=@parent OR parent_run_id=@parent ORDER BY started_at_utc,component;
SELECT s.run_id,s.ordinal,s.name,s.status,s.started_at_utc,s.ended_at_utc,s.duration_seconds
FROM audit.pipeline_steps s JOIN audit.pipeline_runs r ON r.run_id=s.run_id
WHERE r.run_id=@parent OR r.parent_run_id=@parent ORDER BY r.component,s.ordinal;
SELECT q.run_id,q.check_id,q.severity,q.status,q.anomaly_count,q.metric_value
FROM audit.quality_results q JOIN audit.pipeline_runs r ON r.run_id=q.run_id
WHERE r.run_id=@parent OR r.parent_run_id=@parent ORDER BY r.component,q.check_id;
GO
SELECT TOP(1) run_id,started_at_utc,ended_at_utc,
 DATEDIFF_BIG(millisecond,started_at_utc,ended_at_utc)/1000.0 AS elapsed_seconds
FROM audit.pipeline_runs WHERE component='e2e' AND mode='execute' AND status='PASS'
ORDER BY ended_at_utc DESC,run_id DESC;
GO
-- Best available publication evidence, not an exact COMMIT timestamp.
-- Child PASS establishes successful mart runner completion even when parent later fails.
SELECT TOP(1) run_id,parent_run_id,ended_at_utc AS last_confirmed_mart_completion_utc
FROM audit.pipeline_runs WHERE component='mart' AND mode='execute' AND status='PASS'
ORDER BY ended_at_utc DESC,run_id DESC;
GO
SELECT component,mode,status,COUNT_BIG(*) AS runs FROM audit.pipeline_runs
GROUP BY component,mode,status ORDER BY component,mode,status;

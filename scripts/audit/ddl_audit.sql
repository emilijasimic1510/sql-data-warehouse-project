-- Explicit Phase 2C deployment: only new audit objects, no business DDL or data changes.
USE DataWarehouse;
GO
IF DB_NAME() <> N'DataWarehouse'
    THROW 51000, 'Unexpected database', 1;
IF SCHEMA_ID(N'audit') IS NULL EXEC(N'CREATE SCHEMA audit');
GO
IF OBJECT_ID(N'audit.pipeline_runs', N'U') IS NULL
CREATE TABLE audit.pipeline_runs (
    run_id uniqueidentifier NOT NULL PRIMARY KEY,
    started_at_utc datetime2(3) NOT NULL,
    ended_at_utc datetime2(3) NULL,
    status varchar(12) NOT NULL CHECK (status IN ('RUNNING', 'PASS', 'FAIL')),
    mode varchar(20) NOT NULL CHECK (mode IN ('execute', 'quality-only')),
    error nvarchar(2000) NULL
);
IF OBJECT_ID(N'audit.pipeline_steps', N'U') IS NULL
CREATE TABLE audit.pipeline_steps (
    run_id uniqueidentifier NOT NULL REFERENCES audit.pipeline_runs(run_id),
    ordinal int NOT NULL,
    name varchar(40) NOT NULL,
    status varchar(12) NOT NULL CHECK (status IN ('PASS', 'FAIL', 'SKIPPED')),
    started_at_utc datetime2(3) NULL,
    ended_at_utc datetime2(3) NULL,
    duration_seconds float NOT NULL,
    error nvarchar(2000) NULL,
    PRIMARY KEY (run_id, ordinal)
);
IF OBJECT_ID(N'audit.quality_results', N'U') IS NULL
CREATE TABLE audit.quality_results (
    run_id uniqueidentifier NOT NULL REFERENCES audit.pipeline_runs(run_id),
    check_id varchar(20) NOT NULL,
    severity varchar(7) NOT NULL CHECK (severity IN ('ERROR', 'WARNING')),
    status varchar(12) NOT NULL CHECK (status IN ('PASS', 'ERROR', 'WARNING', 'INFO')),
    anomaly_count bigint NULL,
    metric_value bigint NULL,
    duration_seconds float NOT NULL,
    error nvarchar(2000) NULL,
    PRIMARY KEY (run_id, check_id)
);
GO

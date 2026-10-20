-- Explicit additive migration. Existing rows and constraints are retained.
SET XACT_ABORT ON;
IF DB_NAME()<>N'DataWarehouse' THROW 51300,'Unexpected audit migration database',1;
BEGIN TRY
 BEGIN TRANSACTION;
 IF OBJECT_ID(N'audit.pipeline_runs',N'U') IS NULL THROW 51300,'Phase 2C audit deployment required',1;
 IF COL_LENGTH(N'audit.pipeline_runs',N'parent_run_id') IS NULL
  ALTER TABLE audit.pipeline_runs ADD parent_run_id uniqueidentifier NULL;
 IF COL_LENGTH(N'audit.pipeline_runs',N'component') IS NULL
  ALTER TABLE audit.pipeline_runs ADD component varchar(20) NOT NULL
   CONSTRAINT DF_audit_component DEFAULT 'warehouse' WITH VALUES;
 IF COL_LENGTH(N'audit.pipeline_runs',N'summary_json') IS NULL
  ALTER TABLE audit.pipeline_runs ADD summary_json nvarchar(max) NULL;
 IF COL_LENGTH(N'audit.pipeline_runs',N'failure_stage') IS NULL
  ALTER TABLE audit.pipeline_runs ADD failure_stage varchar(40) NULL;
 IF NOT EXISTS(SELECT 1 FROM sys.foreign_keys WHERE name=N'FK_audit_parent_run' AND parent_object_id=OBJECT_ID(N'audit.pipeline_runs'))
  EXEC(N'ALTER TABLE audit.pipeline_runs ADD CONSTRAINT FK_audit_parent_run FOREIGN KEY(parent_run_id) REFERENCES audit.pipeline_runs(run_id)');
 IF NOT EXISTS(SELECT 1 FROM sys.check_constraints WHERE name=N'CK_audit_component' AND parent_object_id=OBJECT_ID(N'audit.pipeline_runs'))
  EXEC(N'ALTER TABLE audit.pipeline_runs ADD CONSTRAINT CK_audit_component CHECK(component IN (''warehouse'',''mart'',''e2e''))');
 IF NOT EXISTS(SELECT 1 FROM sys.check_constraints WHERE name=N'CK_audit_summary_json' AND parent_object_id=OBJECT_ID(N'audit.pipeline_runs'))
  EXEC(N'ALTER TABLE audit.pipeline_runs ADD CONSTRAINT CK_audit_summary_json CHECK(summary_json IS NULL OR ISJSON(summary_json)=1)');
 IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name=N'IX_audit_parent_run' AND object_id=OBJECT_ID(N'audit.pipeline_runs'))
  EXEC(N'CREATE INDEX IX_audit_parent_run ON audit.pipeline_runs(parent_run_id,started_at_utc)');
 -- Reject incompatible pre-existing column definitions; rollback any additions.
 IF EXISTS(SELECT 1 FROM (VALUES ('parent_run_id','uniqueidentifier',16,1),('component','varchar',20,0),
   ('summary_json','nvarchar',-1,1),('failure_stage','varchar',40,1)) e(name,type_name,max_length,is_nullable)
  LEFT JOIN sys.columns c ON c.object_id=OBJECT_ID(N'audit.pipeline_runs') AND c.name=e.name
  WHERE c.column_id IS NULL OR TYPE_NAME(c.user_type_id)<>e.type_name OR c.max_length<>e.max_length OR c.is_nullable<>e.is_nullable)
  THROW 51301,'Incompatible Phase 4B audit columns',1;
 COMMIT;
END TRY
BEGIN CATCH
 IF XACT_STATE()<>0 ROLLBACK;
 THROW;
END CATCH;

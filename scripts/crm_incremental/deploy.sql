-- Phase 3B explicit deployment, version 1. No drops, no changes outside crm_incremental.
-- One batch; run via python -m crm_incremental.deploy (checks expected instance first).
SET NOCOUNT ON;
SET XACT_ABORT ON;
IF DB_NAME()<>N'DataWarehouse' THROW 51190, 'Deployment target must be DataWarehouse', 1;
IF @@TRANCOUNT<>0 THROW 51190, 'Deployment requires no outer transaction', 1;
BEGIN TRY
 BEGIN TRANSACTION;
 DECLARE @lock int;
 EXEC @lock=sys.sp_getapplock @Resource=N'crm_incremental.loader.v1', @LockMode='Exclusive',
      @LockOwner='Transaction', @LockTimeout=10000;
 IF @lock<0 THROW 51101, 'Deployment lock unavailable', 1;
 IF SCHEMA_ID(N'crm_incremental') IS NULL EXEC(N'CREATE SCHEMA crm_incremental');
 DECLARE @signature varchar(64), @stored varchar(64), @version nvarchar(20);
 DECLARE @signature_sql nvarchar(max)=N'SELECT @signature=CONVERT(varchar(64),HASHBYTES(''SHA2_256'',CONVERT(nvarchar(max),(
 SELECT o.name,o.type,OBJECT_DEFINITION(o.object_id) AS definition,
  (SELECT c.name,TYPE_NAME(c.user_type_id) AS datatype,c.max_length,c.precision,c.scale,c.is_nullable,
          c.is_identity,c.is_computed,c.collation_name,OBJECT_DEFINITION(c.default_object_id) AS default_definition
   FROM sys.columns c WHERE c.object_id=o.object_id ORDER BY c.column_id FOR XML PATH(''column''),TYPE) AS columns,
  (SELECT i.name,i.is_unique,i.is_primary_key,i.is_disabled,i.type,i.filter_definition,
      (SELECT COL_NAME(ic.object_id,ic.column_id) AS column_name,ic.key_ordinal,ic.is_descending_key,ic.is_included_column
       FROM sys.index_columns ic WHERE ic.object_id=i.object_id AND ic.index_id=i.index_id
       ORDER BY ic.index_column_id FOR XML PATH(''index_column''),TYPE) AS index_columns
   FROM sys.indexes i WHERE i.object_id=o.object_id ORDER BY i.index_id FOR XML PATH(''index''),TYPE) AS indexes,
  (SELECT k.name,k.is_disabled,k.is_not_trusted,k.delete_referential_action,k.update_referential_action,
      (SELECT COL_NAME(f.parent_object_id,f.parent_column_id) AS source_column,
       OBJECT_SCHEMA_NAME(f.referenced_object_id) AS target_schema,OBJECT_NAME(f.referenced_object_id) AS target_table,
       COL_NAME(f.referenced_object_id,f.referenced_column_id) AS target_column
       FROM sys.foreign_key_columns f WHERE f.constraint_object_id=k.object_id
       ORDER BY f.constraint_column_id FOR XML PATH(''mapping''),TYPE) AS mappings
   FROM sys.foreign_keys k WHERE k.parent_object_id=o.object_id ORDER BY k.name FOR XML PATH(''fk''),TYPE) AS foreign_keys,
  (SELECT ch.name,ch.is_disabled,ch.is_not_trusted,ch.definition FROM sys.check_constraints ch
   WHERE ch.parent_object_id=o.object_id ORDER BY ch.name FOR XML PATH(''check''),TYPE) AS checks
 FROM sys.objects o WHERE o.schema_id=SCHEMA_ID(N''crm_incremental'')
 ORDER BY o.name,o.type FOR XML PATH(''object''),TYPE
))),2);';
 IF EXISTS (SELECT 1 FROM sys.objects WHERE schema_id=SCHEMA_ID(N'crm_incremental'))
 BEGIN
   SELECT @stored=CONVERT(varchar(64),value) FROM sys.extended_properties
       WHERE class=3 AND major_id=SCHEMA_ID(N'crm_incremental') AND name=N'schema_signature';
   SELECT @version=CONVERT(nvarchar(20),value) FROM sys.extended_properties
       WHERE class=3 AND major_id=SCHEMA_ID(N'crm_incremental') AND name=N'contract_version';
   EXEC sys.sp_executesql @signature_sql,N'@signature varchar(64) OUTPUT',@signature OUTPUT;
   IF @version IS NULL OR @version<>N'1' OR @stored IS NULL OR @stored<>@signature
       THROW 51191, 'Incompatible or altered incremental schema; explicit migration required', 1;
 END
 ELSE
 BEGIN
CREATE TABLE crm_incremental.attempts (
    attempt_id uniqueidentifier NOT NULL CONSTRAINT PK_ci_attempts PRIMARY KEY,
    batch_id varchar(70) COLLATE Latin1_General_100_BIN2 NOT NULL,
    content_sha256 char(64) COLLATE Latin1_General_100_BIN2 NOT NULL,
    package_type varchar(10) NOT NULL CHECK (package_type IN ('snapshot','delta')),
    status varchar(10) NOT NULL DEFAULT 'RUNNING' CHECK (status IN ('RUNNING','APPLIED','REPLAY')),
    started_at_utc datetime2(6) NOT NULL DEFAULT SYSUTCDATETIME(),
    ended_at_utc datetime2(6) NULL,
    input_events int NOT NULL CHECK (input_events>0),
    inserted_customers int NOT NULL DEFAULT 0 CHECK (inserted_customers>=0),
    updated_customers int NOT NULL DEFAULT 0 CHECK (updated_customers>=0),
    insert_events int NOT NULL DEFAULT 0 CHECK (insert_events>=0),
    update_events int NOT NULL DEFAULT 0 CHECK (update_events>=0),
    no_change_events int NOT NULL DEFAULT 0 CHECK (no_change_events>=0),
    stale_events int NOT NULL DEFAULT 0 CHECK (stale_events>=0),
    duplicate_events int NOT NULL DEFAULT 0 CHECK (duplicate_events>=0),
    CHECK (LEN(batch_id)=70 AND LEFT(batch_id,6)='batch-'),
    CHECK (content_sha256 NOT LIKE '%[^0-9a-f]%')
);
CREATE INDEX IX_ci_attempts_batch ON crm_incremental.attempts(batch_id,started_at_utc);
CREATE TABLE crm_incremental.batches (
    batch_id varchar(70) COLLATE Latin1_General_100_BIN2 NOT NULL CONSTRAINT PK_ci_batches PRIMARY KEY,
    content_sha256 char(64) COLLATE Latin1_General_100_BIN2 NOT NULL,
    package_type varchar(10) NOT NULL CHECK (package_type IN ('snapshot','delta')),
    input_events int NOT NULL CHECK (input_events>0),
    first_attempt_id uniqueidentifier NOT NULL REFERENCES crm_incremental.attempts(attempt_id),
    committed_at_utc datetime2(6) NOT NULL DEFAULT SYSUTCDATETIME()
);
CREATE TABLE crm_incremental.customers (
    cst_id int NOT NULL CONSTRAINT PK_ci_customers PRIMARY KEY CHECK (cst_id BETWEEN 1900000000 AND 1900000999),
    cst_key nvarchar(50) COLLATE Latin1_General_100_BIN2 NOT NULL CONSTRAINT UQ_ci_customer_number UNIQUE,
    cst_firstname nvarchar(50) NOT NULL CHECK (cst_firstname LIKE N'DemoFirst[_]%'),
    cst_lastname nvarchar(50) NOT NULL CHECK (cst_lastname LIKE N'DemoFamily[_]%'),
    cst_marital_status nvarchar(50) NOT NULL CHECK (cst_marital_status IN (N'Single',N'Married',N'n/a')),
    cst_gndr nvarchar(50) NOT NULL CHECK (cst_gndr IN (N'Female',N'Male',N'n/a')),
    cst_create_date date NOT NULL,
    source_updated_at datetime2(6) NOT NULL,
    last_event_id varchar(68) COLLATE Latin1_General_100_BIN2 NOT NULL,
    business_hash binary(32) NOT NULL,
    CHECK (cst_create_date<=CONVERT(date,source_updated_at)),
    CHECK (cst_key LIKE N'DEMOCRM[0-9][0-9][0-9][0-9]')
);
CREATE TABLE crm_incremental.events (
    event_id varchar(68) COLLATE Latin1_General_100_BIN2 NOT NULL CONSTRAINT PK_ci_events PRIMARY KEY,
    event_hash binary(32) NOT NULL,
    cst_id int NOT NULL REFERENCES crm_incremental.customers(cst_id),
    source_updated_at datetime2(6) NOT NULL,
    business_hash binary(32) NOT NULL,
    batch_id varchar(70) COLLATE Latin1_General_100_BIN2 NOT NULL REFERENCES crm_incremental.batches(batch_id),
    outcome varchar(16) NOT NULL CHECK (outcome IN ('insert','update','no_change','stale')),
    CHECK (LEN(event_id)=68 AND LEFT(event_id,4)='evt-')
);
CREATE INDEX IX_ci_events_customer_time ON crm_incremental.events(cst_id,source_updated_at) INCLUDE (business_hash);
CREATE TABLE crm_incremental.staging (
    attempt_id uniqueidentifier NOT NULL REFERENCES crm_incremental.attempts(attempt_id),
    ordinal int NOT NULL CHECK (ordinal>0),
    event_id varchar(68) COLLATE Latin1_General_100_BIN2 NOT NULL,
    event_hash binary(32) NOT NULL,
    business_hash binary(32) NOT NULL,
    source_updated_at datetime2(6) NOT NULL,
    cst_id int NOT NULL CHECK (cst_id BETWEEN 1900000000 AND 1900000999),
    cst_key nvarchar(50) NOT NULL,
    cst_firstname nvarchar(50) NOT NULL,
    cst_lastname nvarchar(50) NOT NULL,
    cst_marital_status nvarchar(50) NOT NULL CHECK (cst_marital_status IN (N'Single',N'Married',N'n/a')),
    cst_gndr nvarchar(50) NOT NULL CHECK (cst_gndr IN (N'Female',N'Male',N'n/a')),
    cst_create_date date NOT NULL,
    outcome varchar(16) NULL CHECK (outcome IN ('insert','update','no_change','stale','duplicate','batch_replay')),
    CONSTRAINT PK_ci_staging PRIMARY KEY (attempt_id,ordinal)
);
CREATE INDEX IX_ci_staging_events ON crm_incremental.staging(attempt_id,cst_id,source_updated_at,event_id);

 EXEC(N'CREATE OR ALTER PROCEDURE crm_incremental.apply_batch @attempt_id uniqueidentifier
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    BEGIN TRY
        IF @@TRANCOUNT <> 1 OR XACT_STATE() <> 1
            THROW 51100, ''One caller-owned transaction is required'', 1;
        DECLARE @lock_result int;
        EXEC @lock_result = sys.sp_getapplock @Resource=N''crm_incremental.loader.v1'',
            @LockMode=''Exclusive'', @LockOwner=''Transaction'', @LockTimeout=10000;
        IF @lock_result < 0 THROW 51101, ''Incremental loader lock unavailable'', 1;
        DECLARE @batch_id varchar(70), @sha char(64), @kind varchar(10), @count int;
        SELECT @batch_id=batch_id, @sha=content_sha256, @kind=package_type, @count=input_events
        FROM crm_incremental.attempts WHERE attempt_id=@attempt_id AND status=''RUNNING'';
        IF @batch_id IS NULL THROW 51102, ''Missing running attempt'', 1;
        IF @count <> (SELECT COUNT(*) FROM crm_incremental.staging WHERE attempt_id=@attempt_id)
            THROW 51103, ''Staging count mismatch'', 1;
        IF EXISTS (SELECT 1 FROM crm_incremental.batches WHERE batch_id=@batch_id
                   AND (content_sha256<>@sha OR package_type<>@kind OR input_events<>@count))
            THROW 51110, ''Batch identity conflict'', 1;
        IF EXISTS (SELECT event_id FROM crm_incremental.staging WHERE attempt_id=@attempt_id
                   GROUP BY event_id HAVING MIN(CONVERT(char(64),event_hash,2))<>MAX(CONVERT(char(64),event_hash,2)))
            THROW 51111, ''Conflicting event identity within package'', 1;
        IF EXISTS (SELECT 1 FROM crm_incremental.staging s JOIN crm_incremental.events e ON s.event_id=e.event_id
                   WHERE s.attempt_id=@attempt_id AND s.event_hash<>e.event_hash)
            THROW 51111, ''Event identity conflict'', 1;
        IF EXISTS (SELECT 1 FROM crm_incremental.batches WHERE batch_id=@batch_id)
        BEGIN
            UPDATE crm_incremental.staging SET outcome=''batch_replay'' WHERE attempt_id=@attempt_id;
            UPDATE crm_incremental.attempts SET status=''REPLAY'', ended_at_utc=SYSUTCDATETIME(),
                duplicate_events=@count WHERE attempt_id=@attempt_id;
        END
        ELSE
        BEGIN
            IF EXISTS (SELECT cst_id,source_updated_at FROM crm_incremental.staging WHERE attempt_id=@attempt_id
                       GROUP BY cst_id,source_updated_at
                       HAVING MIN(CONVERT(char(64),business_hash,2))<>MAX(CONVERT(char(64),business_hash,2)))
                THROW 51112, ''Ambiguous equal-time values within package'', 1;
            IF EXISTS (SELECT 1 FROM crm_incremental.staging s JOIN crm_incremental.events e
                       ON s.cst_id=e.cst_id AND s.source_updated_at=e.source_updated_at
                       WHERE s.attempt_id=@attempt_id AND s.business_hash<>e.business_hash)
                THROW 51112, ''Ambiguous equal-time values against event ledger'', 1;
            IF EXISTS (SELECT 1 FROM crm_incremental.staging s JOIN crm_incremental.customers c
                       ON s.cst_id=c.cst_id AND s.source_updated_at=c.source_updated_at
                       WHERE s.attempt_id=@attempt_id AND s.business_hash<>c.business_hash)
                THROW 51112, ''Ambiguous equal-time values against current customer'', 1;
            DECLARE @before TABLE (cst_id int PRIMARY KEY, business_hash binary(32));
            INSERT @before SELECT c.cst_id,c.business_hash FROM crm_incremental.customers c
                WHERE EXISTS (SELECT 1 FROM crm_incremental.staging s WHERE s.attempt_id=@attempt_id AND s.cst_id=c.cst_id);
            INSERT crm_incremental.batches (batch_id,content_sha256,package_type,input_events,first_attempt_id)
                VALUES (@batch_id,@sha,@kind,@count,@attempt_id);
            DECLARE @ordinal int, @event_id varchar(68), @event_hash binary(32), @business_hash binary(32),
                @source_time datetime2(6), @id int, @key nvarchar(50), @first nvarchar(50), @last nvarchar(50),
                @marital nvarchar(50), @gender nvarchar(50), @created date, @outcome varchar(16),
                @old_time datetime2(6), @old_hash binary(32);
            DECLARE event_cursor CURSOR LOCAL FAST_FORWARD FOR
                SELECT ordinal,event_id,event_hash,business_hash,source_updated_at,cst_id,cst_key,
                    cst_firstname,cst_lastname,cst_marital_status,cst_gndr,cst_create_date
                FROM crm_incremental.staging WHERE attempt_id=@attempt_id
                ORDER BY cst_id,source_updated_at,event_id,ordinal;
            OPEN event_cursor;
            FETCH NEXT FROM event_cursor INTO @ordinal,@event_id,@event_hash,@business_hash,@source_time,@id,
                @key,@first,@last,@marital,@gender,@created;
            WHILE @@FETCH_STATUS=0
            BEGIN
                IF EXISTS (SELECT 1 FROM crm_incremental.events WHERE event_id=@event_id)
                    SET @outcome=''duplicate'';
                ELSE
                BEGIN
                    SET @old_time=NULL; SET @old_hash=NULL;
                    SELECT @old_time=source_updated_at,@old_hash=business_hash
                        FROM crm_incremental.customers WHERE cst_id=@id;
                    IF @old_time IS NULL
                    BEGIN
                        INSERT crm_incremental.customers
                            (cst_id,cst_key,cst_firstname,cst_lastname,cst_marital_status,cst_gndr,cst_create_date,
                             source_updated_at,last_event_id,business_hash)
                            VALUES (@id,@key,@first,@last,@marital,@gender,@created,@source_time,@event_id,@business_hash);
                        SET @outcome=''insert'';
                    END
                    ELSE IF @source_time < @old_time SET @outcome=''stale'';
                    ELSE
                    BEGIN
                        SET @outcome=CASE WHEN @business_hash=@old_hash THEN ''no_change'' ELSE ''update'' END;
                        -- Equal-time identical business values keep the previously accepted event pointer.
                        IF @source_time > @old_time
                            UPDATE crm_incremental.customers SET cst_key=@key,cst_firstname=@first,cst_lastname=@last,
                                cst_marital_status=@marital,cst_gndr=@gender,cst_create_date=@created,
                                source_updated_at=@source_time,last_event_id=@event_id,business_hash=@business_hash
                            WHERE cst_id=@id;
                    END;
                    INSERT crm_incremental.events (event_id,event_hash,cst_id,source_updated_at,business_hash,batch_id,outcome)
                        VALUES (@event_id,@event_hash,@id,@source_time,@business_hash,@batch_id,@outcome);
                END;
                UPDATE crm_incremental.staging SET outcome=@outcome WHERE attempt_id=@attempt_id AND ordinal=@ordinal;
                FETCH NEXT FROM event_cursor INTO @ordinal,@event_id,@event_hash,@business_hash,@source_time,@id,
                    @key,@first,@last,@marital,@gender,@created;
            END;
            CLOSE event_cursor; DEALLOCATE event_cursor;
            UPDATE crm_incremental.attempts SET status=''APPLIED'',ended_at_utc=SYSUTCDATETIME(),
                inserted_customers=(SELECT COUNT(*) FROM crm_incremental.customers c WHERE
                    EXISTS (SELECT 1 FROM crm_incremental.staging s WHERE s.attempt_id=@attempt_id AND s.cst_id=c.cst_id)
                    AND NOT EXISTS (SELECT 1 FROM @before b WHERE b.cst_id=c.cst_id)),
                updated_customers=(SELECT COUNT(*) FROM crm_incremental.customers c JOIN @before b ON b.cst_id=c.cst_id
                                   WHERE c.business_hash<>b.business_hash),
                insert_events=(SELECT COUNT(*) FROM crm_incremental.staging WHERE attempt_id=@attempt_id AND outcome=''insert''),
                update_events=(SELECT COUNT(*) FROM crm_incremental.staging WHERE attempt_id=@attempt_id AND outcome=''update''),
                no_change_events=(SELECT COUNT(*) FROM crm_incremental.staging WHERE attempt_id=@attempt_id AND outcome=''no_change''),
                stale_events=(SELECT COUNT(*) FROM crm_incremental.staging WHERE attempt_id=@attempt_id AND outcome=''stale''),
                duplicate_events=(SELECT COUNT(*) FROM crm_incremental.staging WHERE attempt_id=@attempt_id AND outcome=''duplicate'')
            WHERE attempt_id=@attempt_id;
        END;
        SELECT status,input_events,inserted_customers,updated_customers,insert_events,update_events,
               no_change_events,stale_events,duplicate_events
        FROM crm_incremental.attempts WHERE attempt_id=@attempt_id;
        -- Caller must consume all results before COMMIT; no nested transaction here.
    END TRY
    BEGIN CATCH
        IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
');

   EXEC sys.sp_executesql @signature_sql,N'@signature varchar(64) OUTPUT',@signature OUTPUT;
   EXEC sys.sp_addextendedproperty @name=N'contract_version',@value=N'1',
       @level0type=N'SCHEMA',@level0name=N'crm_incremental';
   EXEC sys.sp_addextendedproperty @name=N'schema_signature',@value=@signature,
       @level0type=N'SCHEMA',@level0name=N'crm_incremental';
 END;
 COMMIT TRANSACTION;
 SELECT N'VERIFIED' AS deployment_status,@signature AS schema_signature;
END TRY
BEGIN CATCH
 IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
 THROW;
END CATCH;

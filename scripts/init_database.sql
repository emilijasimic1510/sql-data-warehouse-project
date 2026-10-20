/*
Create DataWarehouse and missing schemas without deleting existing data.
Existing objects are left unchanged; this is not a schema migration script.
Run in SSMS as a separate installation step, outside an explicit transaction.
*/
USE master;
GO

IF DB_ID(N'DataWarehouse') IS NULL
    EXEC(N'CREATE DATABASE DataWarehouse');
GO

USE DataWarehouse;
GO

IF SCHEMA_ID(N'bronze') IS NULL
    EXEC(N'CREATE SCHEMA bronze');
GO
IF SCHEMA_ID(N'silver') IS NULL
    EXEC(N'CREATE SCHEMA silver');
GO
IF SCHEMA_ID(N'gold') IS NULL
    EXEC(N'CREATE SCHEMA gold');
GO

/*
=============================================================
Database Creation Script
=============================================================
This script sets up a database called 'DataWarehouse'. 
It first checks if the database already exists. If it does, the 
existing one will be removed and a new one will be created. 

Once the database is ready, three schemas will be added:
'bronze', 'silver', and 'gold'.

Important:
Running this script will erase the existing 'DataWarehouse' 
database (if present) along with all its data. 
Make sure you have a backup before proceeding.
*/


USE master;
GO

-- Drop and recreate the 'DataWarehouse' database
IF EXISTS (SELECT 1 FROM sys.databases WHERE name = 'DataWarehouse')
BEGIN
    ALTER DATABASE DataWarehouse SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
    DROP DATABASE DataWarehouse;
END;
GO

-- Create the 'DataWarehouse' database
CREATE DATABASE DataWarehouse;
GO

USE DataWarehouse;
GO

-- Create Schemas
CREATE SCHEMA bronze;
GO

CREATE SCHEMA silver;
GO

CREATE SCHEMA gold;
GO

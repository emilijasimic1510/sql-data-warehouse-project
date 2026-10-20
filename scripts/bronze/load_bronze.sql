/*
===============================================================================
Stored Procedure: Load Bronze Layer (Source -> Bronze)
===============================================================================
Script Purpose:
    This stored procedure loads data into the 'bronze' schema from external CSV files. 
    It performs the following actions:
    - Truncates the bronze tables before loading data.
    - Uses the `BULK INSERT` command to load data from csv Files to bronze tables.

Parameters:
    @dataset_root: absolute dataset directory on the SQL Server host (or accessible UNC share).
    SQL Server must have file access. A trailing slash is optional.

Usage Example:
    EXEC bronze.load_bronze @dataset_root = N'C:\data\datasets';
===============================================================================
*/
USE DataWarehouse;
GO

CREATE OR ALTER PROCEDURE bronze.load_bronze
    @dataset_root NVARCHAR(4000)
AS
BEGIN
	DECLARE @start_time DATETIME, @end_time DATETIME, @batch_start_time DATETIME, @batch_end_time DATETIME; 
	DECLARE @sql NVARCHAR(MAX), @file_path NVARCHAR(MAX);
	BEGIN TRY
        -- Validate before truncating any table. Normalize separators; keep drive/UNC roots.
        SET @dataset_root = REPLACE(LTRIM(RTRIM(@dataset_root)), N'/', N'\');
        IF @dataset_root IS NULL OR @dataset_root = N''
            THROW 50001, 'dataset_root must be a non-empty absolute path on the SQL Server host.', 1;
        IF NOT ((LEN(@dataset_root) >= 3 AND SUBSTRING(@dataset_root, 2, 2) = N':\'
                 AND LEFT(@dataset_root, 1) LIKE N'[A-Za-z]')
                OR (LEN(@dataset_root) > 2 AND LEFT(@dataset_root, 2) = N'\\'))
            THROW 50002, 'dataset_root must be a Windows drive path or a UNC path.', 1;
        IF RIGHT(@dataset_root, 1) <> N'\'
        BEGIN
            IF LEN(@dataset_root) = 4000
                THROW 50003, 'dataset_root is too long to append a separator.', 1;
            SET @dataset_root += N'\';
        END;
		SET @batch_start_time = GETDATE();
		PRINT '================================================';
		PRINT 'Loading Bronze Layer';
		PRINT '================================================';

		PRINT '------------------------------------------------';
		PRINT 'Loading CRM Tables';
		PRINT '------------------------------------------------';

		SET @start_time = GETDATE();
		PRINT '>> Truncating Table: bronze.crm_cust_info';
		TRUNCATE TABLE bronze.crm_cust_info;
		PRINT '>> Inserting Data Into: bronze.crm_cust_info';
        SET @file_path = @dataset_root + N'source_crm\cust_info.csv';
        -- BULK INSERT requires a literal filename; escape apostrophes in the supplied path.
        SET @sql = N'BULK INSERT bronze.crm_cust_info FROM N'''
            + REPLACE(@file_path, N'''', N'''''')
            + N''' WITH (FIRSTROW = 2, FIELDTERMINATOR = '','', TABLOCK);';
        EXEC sys.sp_executesql @sql;
		SET @end_time = GETDATE();
		PRINT '>> Load Duration: ' + CAST(DATEDIFF(second, @start_time, @end_time) AS NVARCHAR) + ' seconds';
		PRINT '>> -------------';

        SET @start_time = GETDATE();
		PRINT '>> Truncating Table: bronze.crm_product_info';
		TRUNCATE TABLE bronze.crm_product_info;

		PRINT '>> Inserting Data Into: bronze.crm_product_info';
        SET @file_path = @dataset_root + N'source_crm\prd_info.csv';
        -- BULK INSERT requires a literal filename; escape apostrophes in the supplied path.
        SET @sql = N'BULK INSERT bronze.crm_product_info FROM N'''
            + REPLACE(@file_path, N'''', N'''''')
            + N''' WITH (FIRSTROW = 2, FIELDTERMINATOR = '','', TABLOCK);';
        EXEC sys.sp_executesql @sql;
		SET @end_time = GETDATE();
		PRINT '>> Load Duration: ' + CAST(DATEDIFF(second, @start_time, @end_time) AS NVARCHAR) + ' seconds';
		PRINT '>> -------------';

        SET @start_time = GETDATE();
		PRINT '>> Truncating Table: bronze.crm_sales_info';
		TRUNCATE TABLE bronze.crm_sales_info;
		PRINT '>> Inserting Data Into: bronze.crm_sales_info';
        SET @file_path = @dataset_root + N'source_crm\sales_details.csv';
        -- BULK INSERT requires a literal filename; escape apostrophes in the supplied path.
        SET @sql = N'BULK INSERT bronze.crm_sales_info FROM N'''
            + REPLACE(@file_path, N'''', N'''''')
            + N''' WITH (FIRSTROW = 2, FIELDTERMINATOR = '','', TABLOCK);';
        EXEC sys.sp_executesql @sql;
		SET @end_time = GETDATE();
		PRINT '>> Load Duration: ' + CAST(DATEDIFF(second, @start_time, @end_time) AS NVARCHAR) + ' seconds';
		PRINT '>> -------------';

		PRINT '------------------------------------------------';
		PRINT 'Loading ERP Tables';
		PRINT '------------------------------------------------';
		
		SET @start_time = GETDATE();
		PRINT '>> Truncating Table: bronze.erp_location_info';
		TRUNCATE TABLE bronze.erp_location_info;
		PRINT '>> Inserting Data Into: bronze.erp_location_info';
        SET @file_path = @dataset_root + N'source_erp\LOC_A101.csv';
        -- BULK INSERT requires a literal filename; escape apostrophes in the supplied path.
        SET @sql = N'BULK INSERT bronze.erp_location_info FROM N'''
            + REPLACE(@file_path, N'''', N'''''')
            + N''' WITH (FIRSTROW = 2, FIELDTERMINATOR = '','', TABLOCK);';
        EXEC sys.sp_executesql @sql;
		SET @end_time = GETDATE();
		PRINT '>> Load Duration: ' + CAST(DATEDIFF(second, @start_time, @end_time) AS NVARCHAR) + ' seconds';
		PRINT '>> -------------';

		SET @start_time = GETDATE();
		PRINT '>> Truncating Table: bronze.erp_customer_info';
		TRUNCATE TABLE bronze.erp_customer_info;
		PRINT '>> Inserting Data Into: bronze.erp_customer_info';
        SET @file_path = @dataset_root + N'source_erp\CUST_AZ12.csv';
        -- BULK INSERT requires a literal filename; escape apostrophes in the supplied path.
        SET @sql = N'BULK INSERT bronze.erp_customer_info FROM N'''
            + REPLACE(@file_path, N'''', N'''''')
            + N''' WITH (FIRSTROW = 2, FIELDTERMINATOR = '','', TABLOCK);';
        EXEC sys.sp_executesql @sql;
		SET @end_time = GETDATE();
		PRINT '>> Load Duration: ' + CAST(DATEDIFF(second, @start_time, @end_time) AS NVARCHAR) + ' seconds';
		PRINT '>> -------------';

		SET @start_time = GETDATE();
		PRINT '>> Truncating Table: bronze.erp_product_category';
		TRUNCATE TABLE bronze.erp_product_category;
		PRINT '>> Inserting Data Into: bronze.erp_product_category';
        SET @file_path = @dataset_root + N'source_erp\PX_CAT_G1V2.csv';
        -- BULK INSERT requires a literal filename; escape apostrophes in the supplied path.
        SET @sql = N'BULK INSERT bronze.erp_product_category FROM N'''
            + REPLACE(@file_path, N'''', N'''''')
            + N''' WITH (FIRSTROW = 2, FIELDTERMINATOR = '','', TABLOCK);';
        EXEC sys.sp_executesql @sql;
		SET @end_time = GETDATE();
		PRINT '>> Load Duration: ' + CAST(DATEDIFF(second, @start_time, @end_time) AS NVARCHAR) + ' seconds';
		PRINT '>> -------------';

		SET @batch_end_time = GETDATE();
		PRINT '=========================================='
		PRINT 'Loading Bronze Layer is Completed';
        PRINT '   - Total Load Duration: ' + CAST(DATEDIFF(SECOND, @batch_start_time, @batch_end_time) AS NVARCHAR) + ' seconds';
		PRINT '=========================================='
	END TRY
	BEGIN CATCH
		PRINT '=========================================='
		PRINT 'ERROR OCCURED DURING LOADING BRONZE LAYER'
		PRINT 'Error Message: ' + ERROR_MESSAGE();
		PRINT 'Error Number: ' + CAST (ERROR_NUMBER() AS NVARCHAR);
		PRINT 'Error State: ' + CAST (ERROR_STATE() AS NVARCHAR);
		PRINT '==========================================';
        THROW;
	END CATCH
END;
GO

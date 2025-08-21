# Data Warehouse Project

Welcome to the **Data Warehouse Project** repository! 🚀  
This project demonstrates how to design and build a modern data warehouse using the **Medallion Architecture** (Bronze, Silver, Gold). It covers the full pipeline: from ingesting raw data to producing analytics-ready models.

---

## 🏗️ Data Architecture

The data warehouse follows the **Bronze → Silver → Gold** layered approach:

1. **Bronze Layer**: Stores raw data exactly as received from source systems (ERP, CRM) in CSV format.  
2. **Silver Layer**: Cleansed and standardized data prepared for integration and analysis.  
3. **Gold Layer**: Business-ready star schema with fact and dimension tables for reporting.

📌 Example architecture:  
`ERP/CRM CSV → Bronze → Silver → Gold → Analytics`

---

## 📖 Project Overview

This project includes:

- **Data Architecture**: Implementing the Medallion Architecture.  
- **ETL Pipelines**: Loading, cleaning, and transforming ERP and CRM data.  
- **Data Modeling**: Designing `dim_customers`, `dim_products`, and `fact_sales`.  
- **Analytics & Reporting**: Providing insights on customer behavior, product performance, and sales trends.

🎯 Skills demonstrated:  
- SQL Development  
- Data Modeling (Star Schema)  
- ETL Design (Bronze → Silver → Gold)  
- Data Analytics & Reporting  

---

## 📂 Repository Structure
```
data-warehouse-project/
│
├── datasets/                           # Raw datasets (ERP and CRM CSV files)
│
├── docs/                               # Documentation and diagrams
│   ├── data_architecture.drawio        # Architecture diagram
│   ├── data_flow.drawio                # Data flow diagram
│   ├── data_models.drawio              # Star schema diagrams
│   ├── data_catalog.md                 # Business glossary of dimensions and facts
│   ├── naming_conventions.md           # Naming standards (tables, columns, scripts)
│
├── scripts/                            # SQL scripts for ETL and modeling
│   ├── bronze/                         # Create and load Bronze tables
│   ├── silver/                         # Transform and standardize Silver tables
│   ├── gold/                           # Build Gold fact and dimension views
│
├── tests/                              # Data quality checks
│
├── README.md                           # Project overview and usage
├── LICENSE                             # License file
└── .gitignore                          # Ignore unnecessary files in Git
```

---

## 🚀 How to Use

1. **Clone the repo**  
   ```bash
   git clone https://github.com/<your-username>/data-warehouse-project.git
   ```

2. **Set up the database**  
   - Install SQL Server Express (or any SQL engine you prefer).  
   - Run scripts from `/scripts/bronze`, `/scripts/silver`, `/scripts/gold` in order.  

3. **Load datasets**  
   - Place ERP and CRM CSV files in `/datasets/`.  
   - Run ETL scripts to load them into the database.  

4. **Explore analytics**  
   - Query `dim_customers`, `dim_products`, and `fact_sales`.  
   - Build your own reports/dashboards in Power BI, Tableau, or SQL.  

---

## 🛡️ License
This project is licensed under the [MIT License](LICENSE). You are free to use and adapt it with attribution.

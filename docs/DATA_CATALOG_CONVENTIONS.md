# Data Catalog — Gold Layer

## Overview
The **Gold Layer** is the business-level data representation designed for analytics and reporting.  
It follows a **star schema** with **dimension** and **fact** objects.

---

## 1) `dim_customers`
**Purpose:** Stores customer details enriched with demographic and geographic data.

### Columns

| Column Name       | Data Type    | Description                                                                                  |
|-------------------|--------------|----------------------------------------------------------------------------------------------|
| `customer_key`    | INT          | Surrogate key uniquely identifying each customer record in the dimension table.             |
| `customer_id`     | INT          | Unique numerical identifier assigned to each customer (from CRM).                           |
| `customer_number` | NVARCHAR(50) | Alphanumeric identifier representing the customer, used for tracking and referencing.       |
| `first_name`      | NVARCHAR(50) | The customer's first name, as recorded in the system.                                       |
| `last_name`       | NVARCHAR(50) | The customer's last name or family name.                                                    |
| `country`         | NVARCHAR(50) | The country of residence for the customer (e.g., `Australia`).                              |
| `marital_status`  | NVARCHAR(50) | The marital status of the customer (e.g., `Married`, `Single`).                             |
| `gender`          | NVARCHAR(50) | The gender of the customer (e.g., `Male`, `Female`, `n/a`).                                 |
| `birthdate`       | DATE         | The date of birth of the customer (format `YYYY-MM-DD`, e.g., `1971-10-06`).                |
| `create_date`     | DATE         | The date when the customer record was created in the CRM system.                            |

---

## 2) `dim_products`
**Purpose:** Provides information about products and their attributes.

### Columns

| Column Name      | Data Type    | Description                                                                                  |
|------------------|--------------|----------------------------------------------------------------------------------------------|
| `product_key`    | INT          | Surrogate key uniquely identifying each product record in the product dimension table.      |
| `product_id`     | INT          | Unique identifier assigned to the product for internal tracking and referencing.            |
| `product_number` | NVARCHAR(50) | Structured alphanumeric code representing the product; used for categorization.            |
| `product_name`   | NVARCHAR(50) | Descriptive name of the product (e.g., type, color, size).                                  |
| `category_id`    | NVARCHAR(50) | Identifier for the product’s category; links to high-level classification.                  |
| `category`       | NVARCHAR(50) | Broader classification of the product (e.g., `Bikes`, `Components`).                        |
| `subcategory`    | NVARCHAR(50) | More detailed classification within the category (e.g., `Road Bikes`).                      |
| `maintenance`    | NVARCHAR(50) | Indicates whether the product requires maintenance (e.g., `Yes`, `No`).                     |
| `cost`           | INT          | The cost or base price of the product, in currency units.                                   |
| `product_line`   | NVARCHAR(50) | The product line or series (e.g., `Road`, `Mountain`).                                      |
| `start_date`     | DATE         | The date when the product became available for sale or use.                                 |

---

## 3) `fact_sales`
**Purpose:** Stores transactional sales data for analytical purposes.

### Columns

| Column Name     | Data Type    | Description                                                                                   |
|-----------------|--------------|-----------------------------------------------------------------------------------------------|
| `order_number`  | NVARCHAR(50) | Unique alphanumeric identifier for each sales order (e.g., `SO54496`).                        |
| `product_key`   | INT          | Surrogate key linking the order to the product dimension (`dim_products`).                    |
| `customer_key`  | INT          | Surrogate key linking the order to the customer dimension (`dim_customers`).                  |
| `order_date`    | DATE         | The date when the order was placed.                                                           |
| `shipping_date` | DATE         | The date when the order was shipped to the customer.                                          |
| `due_date`      | DATE         | The date when payment for the order was due.                                                  |
| `sales_amount`  | INT          | Total monetary value of the sale for the line item (e.g., `250`).                             |
| `quantity`      | INT          | Number of units of the product ordered for the line item (e.g., `1`).                         |
| `price`         | INT          | Price per unit of the product for the line item, in whole currency units (e.g., `25`).        |

---

### Notes
- `dim_products` includes only active products (as defined in the corresponding view logic).
- Surrogate keys (`customer_key`, `product_key`) are generated in Gold views and used as foreign keys in `fact_sales`.
- Column names mirror those produced by the Gold views to keep schema and documentation aligned.

-- ============================================================
-- Star schema for Sales_Dashboard_Data.xlsx
-- One fact table (fact_sales) + 5 dimension tables + data_dictionary
-- Run in this order: dims -> fact -> data_dictionary
-- ============================================================

DROP TABLE IF EXISTS fact_sales CASCADE;
DROP TABLE IF EXISTS dim_customer CASCADE;
DROP TABLE IF EXISTS dim_product CASCADE;
DROP TABLE IF EXISTS dim_location CASCADE;
DROP TABLE IF EXISTS dim_ship_mode CASCADE;
DROP TABLE IF EXISTS dim_date CASCADE;
DROP TABLE IF EXISTS data_dictionary CASCADE;

-- ---------------- Dimensions ----------------

CREATE TABLE dim_customer (
    customer_key   INTEGER PRIMARY KEY,
    customer_id    TEXT NOT NULL UNIQUE,
    customer_name  TEXT NOT NULL,
    segment        TEXT NOT NULL
);

CREATE TABLE dim_product (
    product_key    INTEGER PRIMARY KEY,
    product_id     TEXT NOT NULL UNIQUE,
    category       TEXT NOT NULL,
    sub_category   TEXT NOT NULL,
    product_name   TEXT NOT NULL
);

CREATE TABLE dim_location (
    location_key   INTEGER PRIMARY KEY,
    city           TEXT NOT NULL,
    state          TEXT NOT NULL,
    postal_code    INTEGER NOT NULL,
    region         TEXT NOT NULL,
    country        TEXT NOT NULL
);

CREATE TABLE dim_ship_mode (
    ship_mode_key  INTEGER PRIMARY KEY,
    ship_mode      TEXT NOT NULL UNIQUE
);

CREATE TABLE dim_date (
    date_key       INTEGER PRIMARY KEY,   -- YYYYMMDD
    date           DATE NOT NULL UNIQUE,
    year           INTEGER NOT NULL,
    quarter        TEXT NOT NULL,
    month          INTEGER NOT NULL,
    month_name     TEXT NOT NULL,
    day            INTEGER NOT NULL,
    day_name       TEXT NOT NULL
);

-- ---------------- Fact table ----------------
-- Grain: one row per sales line item (source Row ID)
-- dim_date is a role-playing dimension: order_date_key and ship_date_key both reference it.

CREATE TABLE fact_sales (
    sales_key       INTEGER PRIMARY KEY,
    order_id        TEXT NOT NULL,
    order_date_key  INTEGER NOT NULL REFERENCES dim_date(date_key),
    ship_date_key   INTEGER NOT NULL REFERENCES dim_date(date_key),
    customer_key    INTEGER NOT NULL REFERENCES dim_customer(customer_key),
    product_key     INTEGER NOT NULL REFERENCES dim_product(product_key),
    location_key    INTEGER NOT NULL REFERENCES dim_location(location_key),
    ship_mode_key   INTEGER NOT NULL REFERENCES dim_ship_mode(ship_mode_key),
    sales           NUMERIC(12,4) NOT NULL,
    quantity        INTEGER NOT NULL,
    discount        NUMERIC(4,2) NOT NULL,
    profit          NUMERIC(12,4) NOT NULL
);

CREATE INDEX idx_fact_sales_order_date ON fact_sales(order_date_key);
CREATE INDEX idx_fact_sales_customer   ON fact_sales(customer_key);
CREATE INDEX idx_fact_sales_product    ON fact_sales(product_key);
CREATE INDEX idx_fact_sales_location   ON fact_sales(location_key);
CREATE INDEX idx_fact_sales_order_id   ON fact_sales(order_id);

-- ---------------- Central metadata table ----------------
-- One row per (table_name, column_name) across every table above, including this one.

CREATE TABLE data_dictionary (
    table_name          TEXT NOT NULL,
    column_name         TEXT NOT NULL,
    table_description   TEXT NOT NULL,
    column_description  TEXT NOT NULL,
    PRIMARY KEY (table_name, column_name)
);

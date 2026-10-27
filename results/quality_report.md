# Data-quality report (real pipeline run)

Raw rows: 5,050 customers, 15,150 orders, 500 products. Clean rows kept: 4,479 / 11,043 / 480. Quarantined: 4,698 rows (22.7% of all raw rows) — every one listed in `data/quarantine.csv` with its reason; nothing was silently dropped or imputed.

## Quality scorecard (fraction of checks passing)

| Dimension | Before | After |
|---|---:|---:|
| Completeness | 0.9977 | 1.0000 |
| Validity | 0.9843 | 1.0000 |
| Uniqueness | 0.9868 | 1.0000 |
| Consistency | 0.4519 | 1.0000 |
| Referential Integrity | 0.9835 | 1.0000 |
| Overall | 0.8808 | 1.0000 |

## Quarantine reasons

| Reason | Rows |
|---|---:|
| orphan_customer_id | 1744 |
| invalid_status | 1022 |
| orphan_product_id | 672 |
| missing_or_invalid_email | 244 |
| missing_or_bad_signup_date | 194 |
| exact_duplicate_row | 176 |
| missing_or_nonpositive_amount | 163 |
| missing_or_bad_order_date | 119 |
| duplicate_order_id | 88 |
| missing_or_nonpositive_quantity | 83 |
| order_before_signup | 80 |
| invalid_age | 45 |
| duplicate_email | 38 |
| missing_or_nonpositive_price | 15 |
| duplicate_customer_id | 10 |
| duplicate_sku | 5 |

## SQL validation gate

Every check in `sql/validate.sql` returns 0 violations on the cleaned tables loaded in `data/ecommerce.sqlite`:

| Check | Violations |
|---|---:|
| customers_null_email | 0 |
| customers_duplicate_customer_id | 0 |
| customers_duplicate_email | 0 |
| customers_bad_age | 0 |
| customers_bad_country | 0 |
| customers_bad_signup_date | 0 |
| products_duplicate_product_id | 0 |
| products_duplicate_sku | 0 |
| products_bad_price | 0 |
| products_bad_category | 0 |
| orders_duplicate_order_id | 0 |
| orders_bad_amount | 0 |
| orders_bad_quantity | 0 |
| orders_bad_status | 0 |
| orders_bad_order_date | 0 |
| orders_orphan_customer | 0 |
| orders_orphan_product | 0 |
| orders_before_signup | 0 |

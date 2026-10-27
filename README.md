# Data Cleaning & Data-Quality Pipeline — E-commerce Orders

A Data Analyst's end-to-end data-quality pipeline: profile messy raw data,
clean it with explicit auditable rules, quarantine what can't be trusted,
and prove the result with a SQL validation gate.

## Business question

An e-commerce company's orders, customers and products tables feed its
revenue reports — but the data arrives messy: duplicate rows, missing
emails, unparseable dates, 15 spellings of the same country, orders
pointing at customers who don't exist. **Can the data be trusted for
reporting — and how much of it has to be thrown out to get there?**

## Approach

1. **Data** (`src/generate_data.py`): 5,050 customers, 15,150 orders and
   500 products of synthetic but realistic e-commerce data (fixed seed
   `20261027`, fully reproducible), with defects injected deliberately:
   exact-duplicate rows, missing/malformed emails, bad dates, invalid
   ages, orphan foreign keys, non-positive amounts, impossible order
   dates, and inconsistent enum spellings. Ground-truth defect counts
   are recorded in `data/ground_truth.json`.
   > The data is **synthetic** — no real customers. Every number below is
   > the real output of running the included code — nothing hand-written.
2. **Cleaning** (`src/pipeline.py`, pandas): explicit rules, applied in a
   fixed order. A row that fails a rule is **quarantined, not silently
   fixed** — it lands in `data/quarantine.csv` with its reason, so every
   dropped row is auditable. Nothing is imputed: no missing email, date
   or price is ever guessed. Standardisation is limited to what is safe:
   trimming whitespace, lower-casing statuses, mapping country/category
   spellings to canonical values.
3. **Validation** (`sql/validate.sql`): 18 SQL checks run against the
   cleaned tables in SQLite (`data/ecommerce.sqlite`) — nulls, duplicates,
   out-of-range values, bad enums, orphan keys, orders predating signup.
   The run fails unless every check returns **0 violations**.
4. **Scorecard**: five data-quality dimensions (completeness, validity,
   uniqueness, consistency, referential integrity) scored before vs after.

## Results (real run output, `results/quality_report.json`)

### What survived

| Table | Raw rows | Clean rows | Kept |
|---|---|---:|---:|
| Customers | 5,050 | 4,479 | 88.7% |
| Orders | 15,150 | 11,043 | 72.9% |
| Products | 500 | 480 | 96.0% |

**4,698 rows (22.7% of all raw rows) were quarantined** — each one listed
in `data/quarantine.csv` with its reason.

### Why rows were quarantined

| Reason | Rows |
|---|---:|
| Orphan customer_id | 1,744 |
| Invalid status (`unknown_status`) | 1,022 |
| Orphan product_id | 672 |
| Missing or invalid email | 244 |
| Missing or bad signup date | 194 |
| Exact duplicate row | 176 |
| Missing or non-positive amount | 163 |
| Missing or bad order date | 119 |
| Duplicate order_id | 88 |
| Missing or non-positive quantity | 83 |
| Order before signup | 80 |
| Invalid age | 45 |
| Duplicate email | 38 |
| Missing or non-positive price | 15 |
| Duplicate customer_id | 10 |
| Duplicate SKU | 5 |

### Quality scorecard (fraction of checks passing)

| Dimension | Before | After |
|---|---:|---:|
| Completeness | 0.9977 | 1.0000 |
| Validity | 0.9843 | 1.0000 |
| Uniqueness | 0.9868 | 1.0000 |
| Consistency | 0.4519 | 1.0000 |
| Referential integrity | 0.9835 | 1.0000 |
| **Overall** | **0.8808** | **1.0000** |

### SQL validation gate: 18/18 checks pass, 0 violations

### Findings worth saying in an interview

- **Consistency was the worst dimension (0.4519).** The raw data had 15
  spellings of 5 countries (`USA`, `US`, `United States`, `usa`,
  `U.S.A.`…), 12 status spellings and 11 category spellings. A `GROUP BY
  country` on the raw data would have split the US into five buckets and
  silently undercounted every metric — standardisation is a reporting
  correctness fix, not cosmetics.
- **Bad data cascades.** Only 300 orders pointed at customer IDs that
  never existed — but 1,744 orders were quarantined as orphans, because
  1,446 of them belonged to customers quarantined for bad emails, bad
  signup dates or invalid ages. One bad customer record kills ~3 orders
  with it, so the customer table is where quality work pays off most.
- **27% of orders were unusable for revenue reporting.** Amounts that
  were zero, negative or missing (163), orders with no valid date (119),
  and orders for products/customers that don't exist — reporting on the
  raw tables would have overstated or understated revenue with no way to
  tell which.
- **Quarantine, don't delete silently.** Every dropped row is kept with
  its reason, so the business can decide what to fix upstream (e.g. the
  1,022 `unknown_status` orders are a source-system bug, not a data
  problem) instead of the analyst hiding the loss.

## How to run

```bash
python3 src/generate_data.py   # builds data/*_raw.csv (+ ground_truth.json)
python3 src/pipeline.py          # profiles, cleans, validates -> results/
sqlite3 data/ecommerce.sqlite < sql/validate.sql   # SQL gate on its own
```

Requires: Python 3, `pandas`, `numpy`.

## Files

| Path | What |
|---|---|
| `src/generate_data.py` | Synthetic raw-data generator (seeded, reproducible) |
| `src/pipeline.py` | Profiling, cleaning, quarantine, scoring, SQL gate |
| `sql/validate.sql` | 18 SQL validation checks (must all return 0) |
| `data/` | `*_raw.csv`, `*_clean.csv`, `quarantine.csv`, `ecommerce.sqlite`, `ground_truth.json` |
| `results/` | `quality_report.json`, `quality_report.md` |

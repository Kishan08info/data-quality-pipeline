"""Generate synthetic raw e-commerce data with realistic data-quality defects.

The raw files are intentionally messy, the way data actually arrives from
web forms, imports and third-party feeds: duplicate rows, missing values,
bad dates, inconsistent spellings, orphan foreign keys, out-of-range
numbers. Every defect is injected deliberately (fixed seed 20261027) so the
cleaning pipeline's detections can be checked against known ground truth.

Tables:
  customers.csv  5,000 customers
  orders.csv    15,000 orders
  products.csv     500 products

Run:  python3 src/generate_data.py
"""

import json
import random
import string
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

SEED = 20261027
rng = random.Random(SEED)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

FIRST = ["Ava", "Liam", "Maya", "Noah", "Zoe", "Ethan", "Priya", "Lucas",
         "Nora", "Owen", "Ivy", "Caleb", "Rosa", "Felix", "Tara", "Hugo",
         "Lena", "Omar", "June", "Silas"]
LAST = ["Patel", "Nguyen", "Garcia", "Kim", "Okafor", "Smith", "Rossi",
        "Chen", "Meyer", "Singh", "Lopez", "Kaur", "Novak", "Ali", "Berg",
        "Costa", "Haddad", "Fischer", "Rao", "Dubois"]

COUNTRY_VARIANTS = ["USA", "US", "United States", "usa", "U.S.A.",
                    "Canada", "CA", "canada", "UK", "United Kingdom", "GB",
                    "Australia", "AU", "Germany", "DE"]
COUNTRY_CANON = {"USA": "US", "US": "US", "United States": "US",
                 "usa": "US", "U.S.A.": "US", "Canada": "CA", "CA": "CA",
                 "canada": "CA", "UK": "GB", "United Kingdom": "GB",
                 "GB": "GB", "Australia": "AU", "AU": "AU",
                 "Germany": "DE", "DE": "DE"}

CATEGORIES = ["Electronics", "electronics", "ELECTRONICS", "Home & Garden",
              "home & garden", "Clothing", "clothing", "Sports", "sports",
              "Books", "books"]
STATUS_VARIANTS = ["shipped", "SHIPPED", "Shipped ", "delivered",
                   "Delivered", "cancelled", "CANCELLED", "pending",
                   "Pending", "returned", "unknown_status", " shipped"]


def rand_date(start: date, end: date) -> date:
    return start + timedelta(days=rng.randrange((end - start).days + 1))


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    injected: dict[str, int] = {}

    # ---------------- customers ----------------
    customers = []
    for i in range(1, 5001):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        customers.append({
            "customer_id": i,
            "email": f"{first.lower()}.{last.lower()}{i}@example.com",
            "first_name": first,
            "last_name": last,
            "country": rng.choice(COUNTRY_VARIANTS),
            "signup_date": rand_date(date(2024, 1, 1),
                                     date(2026, 9, 30)).isoformat(),
            "age": rng.randint(18, 75),
        })
    df_c = pd.DataFrame(customers)

    # exact duplicate rows (whole-row copies)
    dup_rows = df_c.sample(n=50, random_state=SEED)
    df_c = pd.concat([df_c, dup_rows], ignore_index=True)
    injected["customers_exact_duplicate_rows"] = 50

    # missing emails
    idx = df_c.sample(n=150, random_state=SEED + 1).index
    df_c.loc[idx, "email"] = None
    injected["customers_missing_email"] = 150

    # malformed emails (no @, or no domain)
    idx = df_c.sample(n=100, random_state=SEED + 2).index
    bad = ["no-at-sign.example.com", "missing-domain@",
           "double@@example.com", "spaces in@email.com"]
    df_c.loc[idx, "email"] = [rng.choice(bad) for _ in idx]
    injected["customers_malformed_email"] = 100

    # missing signup dates
    idx = df_c.sample(n=100, random_state=SEED + 3).index
    df_c.loc[idx, "signup_date"] = None
    injected["customers_missing_signup_date"] = 100

    # unparseable signup dates
    idx = df_c.sample(n=100, random_state=SEED + 4).index
    bad_dates = ["2026-13-45", "not-a-date", "32/01/2025", "2025-02-30"]
    df_c.loc[idx, "signup_date"] = [rng.choice(bad_dates) for _ in idx]
    injected["customers_bad_signup_date"] = 100

    # invalid ages (negative, >120, or text) — cast to object first so
    # pandas 3 accepts the mixed-type bad values
    df_c["age"] = df_c["age"].astype(object)
    idx = df_c.sample(n=50, random_state=SEED + 5).index
    bad_ages = [-5, 0, 145, 999, "thirty"]
    df_c.loc[idx, "age"] = [rng.choice(bad_ages) for _ in idx]
    injected["customers_invalid_age"] = 50

    # duplicate email across different customer_ids
    idx = df_c.sample(n=40, random_state=SEED + 6).index
    df_c.loc[idx, "email"] = df_c.loc[
        df_c.sample(n=40, random_state=SEED + 7).index, "email"].values
    injected["customers_duplicate_email_diff_id"] = 40

    df_c.to_csv(DATA / "customers_raw.csv", index=False)

    # ---------------- products ----------------
    products = []
    for i in range(1, 501):
        products.append({
            "product_id": i,
            "sku": f"SKU-{1000 + i}",
            "name": f"Product {i} {rng.choice(['Pro', 'Lite', 'Max', 'Plus'])}",
            "category": rng.choice(CATEGORIES),
            "price": round(rng.uniform(5.0, 499.99), 2),
        })
    df_p = pd.DataFrame(products)

    # duplicate SKU across different product_ids
    idx = df_p.sample(n=5, random_state=SEED + 8).index
    df_p.loc[idx, "sku"] = df_p.loc[
        df_p.sample(n=5, random_state=SEED + 9).index, "sku"].values
    injected["products_duplicate_sku"] = 5

    # missing prices
    idx = df_p.sample(n=10, random_state=SEED + 10).index
    df_p.loc[idx, "price"] = float("nan")
    injected["products_missing_price"] = 10

    # negative prices
    idx = df_p.sample(n=5, random_state=SEED + 11).index
    df_p.loc[idx, "price"] = [-12.99, -0.01, -250.0, -3.5, -99.99][:len(idx)]
    injected["products_negative_price"] = 5

    df_p.to_csv(DATA / "products_raw.csv", index=False)

    # ---------------- orders ----------------
    # Order dates are generated AFTER the customer's signup date (a real
    # order cannot predate signup); a small injected set breaks this rule
    # on purpose so the pipeline's check has something to catch.
    signup_map = {c["customer_id"]: c["signup_date"] for c in customers}
    orders = []
    for i in range(1, 15001):
        cust = rng.randint(1, 5000)
        prod = rng.randint(1, 500)
        sd = date.fromisoformat(signup_map[cust])
        latest = min(date(2026, 10, 15),
                     sd + timedelta(days=rng.randrange(0, 400)))
        od = sd + timedelta(days=rng.randrange(0, (latest - sd).days + 1))
        orders.append({
            "order_id": i,
            "customer_id": cust,
            "product_id": prod,
            "order_date": od.isoformat(),
            "amount": round(rng.uniform(5.0, 899.99), 2),
            "status": rng.choice(STATUS_VARIANTS),
            "quantity": rng.randint(1, 5),
        })
    df_o = pd.DataFrame(orders)

    # orders dated before the customer's signup (impossible in reality)
    # (skip rows whose customer was already made an orphan above)
    idx = [j for j in df_o.sample(n=100, random_state=SEED + 20).index
           if int(df_o.at[j, "customer_id"]) in signup_map]
    for j in idx:
        sd = date.fromisoformat(signup_map[int(df_o.at[j, "customer_id"])])
        df_o.at[j, "order_date"] = (
            sd - timedelta(days=rng.randrange(1, 90))).isoformat()
    injected["orders_before_signup"] = len(idx)

    # exact duplicate order rows
    dup_rows = df_o.sample(n=150, random_state=SEED + 12)
    df_o = pd.concat([df_o, dup_rows], ignore_index=True)
    injected["orders_exact_duplicate_rows"] = 150

    # orphan customer_ids (no such customer)
    idx = df_o.sample(n=300, random_state=SEED + 13).index
    df_o.loc[idx, "customer_id"] = [rng.randint(90001, 99999)
                                    for _ in idx]
    injected["orders_orphan_customer"] = 300

    # orphan product_ids
    idx = df_o.sample(n=200, random_state=SEED + 14).index
    df_o.loc[idx, "product_id"] = [rng.randint(9001, 9999) for _ in idx]
    injected["orders_orphan_product"] = 200

    # non-positive / missing amounts
    idx = df_o.sample(n=200, random_state=SEED + 15).index
    bad_amounts = [0.0, -45.99, -1.0, float("nan")]
    df_o.loc[idx, "amount"] = [rng.choice(bad_amounts) for _ in idx]
    injected["orders_bad_amount"] = 200

    # missing / unparseable order dates
    idx = df_o.sample(n=150, random_state=SEED + 16).index
    bad_dates = [None, "2026-02-30", "not-a-date", "15/13/2025"]
    df_o.loc[idx, "order_date"] = [rng.choice(bad_dates) for _ in idx]
    injected["orders_bad_order_date"] = 150

    # non-positive quantities
    idx = df_o.sample(n=100, random_state=SEED + 17).index
    df_o.loc[idx, "quantity"] = [rng.choice([0, -2, -1]) for _ in idx]
    injected["orders_bad_quantity"] = 100

    # duplicate order_id across different rows (same id, different content)
    idx = df_o.sample(n=75, random_state=SEED + 18).index
    df_o.loc[idx, "order_id"] = df_o.loc[
        df_o.sample(n=75, random_state=SEED + 19).index,
        "order_id"].values
    injected["orders_duplicate_order_id"] = 75

    df_o.to_csv(DATA / "orders_raw.csv", index=False)

    # ground-truth defect counts (for the pipeline's self-check)
    meta = {"seed": SEED, "injected_defects": injected,
            "raw_rows": {"customers": len(df_c), "orders": len(df_o),
                         "products": len(df_p)}}
    (ROOT / "data" / "ground_truth.json").write_text(
        json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()

"""Data-cleaning & data-quality pipeline for synthetic e-commerce data.

What it does
------------
1. Profiles the raw CSVs (row counts, nulls, duplicate rows, per-rule
   violations) — the "before" picture.
2. Cleans each table with explicit, logged rules. Rows that fail a rule are
   NOT silently fixed: they go to a quarantine file with the reason, so
   nothing is invented and every dropped row is auditable.
3. Loads the cleaned tables into SQLite and runs the SQL validation gate
   (sql/validate.sql) — every check must return 0 violations.
4. Scores five data-quality dimensions before vs after
   (completeness, validity, uniqueness, consistency, referential
   integrity) and writes results/quality_report.json + .md.

Nothing is imputed: no missing email, date or price is guessed. A row is
either clean by the rules or quarantined with a reason.

Run:  python3 src/generate_data.py && python3 src/pipeline.py
"""

import json
import re
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RESULTS = ROOT / "results"
SQL = ROOT / "sql"

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
VALID_STATUS = {"shipped", "delivered", "cancelled", "pending", "returned"}
COUNTRY_CANON = {"USA": "US", "US": "US", "United States": "US",
                 "usa": "US", "U.S.A.": "US", "Canada": "CA", "CA": "CA",
                 "canada": "CA", "UK": "GB", "United Kingdom": "GB",
                 "GB": "GB", "Australia": "AU", "AU": "AU",
                 "Germany": "DE", "DE": "DE"}
CATEGORY_CANON = {"electronics": "Electronics",
                  "home & garden": "Home & Garden",
                  "clothing": "Clothing", "sports": "Sports",
                  "books": "Books"}


def is_email(v) -> bool:
    return isinstance(v, str) and bool(EMAIL_RE.match(v.strip()))


def parse_dates(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce", format="mixed")


def quarantine(df: pd.DataFrame, mask: pd.Series, reason: str,
               store: dict) -> pd.DataFrame:
    """Move rows matching mask into the quarantine store; return the rest."""
    bad = df[mask].copy()
    if len(bad):
        bad["quarantine_reason"] = reason
        store.setdefault(reason, []).append(bad)
    return df[~mask].copy()


def clean_customers(raw: pd.DataFrame, store: dict) -> pd.DataFrame:
    df = raw.copy()
    # exact duplicate rows (whole-row copies)
    df = quarantine(df, df.duplicated(keep="first"), "exact_duplicate_row",
                    store)
    # duplicate business key: same customer_id twice
    df = quarantine(df, df.duplicated(subset=["customer_id"], keep="first"),
                    "duplicate_customer_id", store)
    # email must be present and well-formed (never invented)
    bad_email = df["email"].isna() | ~df["email"].map(is_email)
    df = quarantine(df, bad_email, "missing_or_invalid_email", store)
    # signup date must parse
    parsed = parse_dates(df["signup_date"])
    df = quarantine(df, parsed.isna(), "missing_or_bad_signup_date", store)
    df["signup_date"] = parsed.dt.date.astype(str)
    # age must be a number in 1..120
    age = pd.to_numeric(df["age"], errors="coerce")
    df = quarantine(df, age.isna() | (age < 1) | (age > 120),
                    "invalid_age", store)
    df["age"] = pd.to_numeric(df["age"], errors="coerce").astype(int)
    # one email per customer
    df = quarantine(df, df.duplicated(subset=["email"], keep="first"),
                    "duplicate_email", store)
    # standardise: trim names, canonical country
    df["first_name"] = df["first_name"].astype(str).str.strip()
    df["last_name"] = df["last_name"].astype(str).str.strip()
    df["country"] = df["country"].astype(str).str.strip().map(COUNTRY_CANON)
    df["email"] = df["email"].astype(str).str.strip().str.lower()
    return df.reset_index(drop=True)


def clean_products(raw: pd.DataFrame, store: dict) -> pd.DataFrame:
    df = raw.copy()
    df = quarantine(df, df.duplicated(keep="first"), "exact_duplicate_row",
                    store)
    df = quarantine(df, df.duplicated(subset=["product_id"], keep="first"),
                    "duplicate_product_id", store)
    df = quarantine(df, df.duplicated(subset=["sku"], keep="first"),
                    "duplicate_sku", store)
    price = pd.to_numeric(df["price"], errors="coerce")
    df = quarantine(df, price.isna() | (price <= 0),
                    "missing_or_nonpositive_price", store)
    df["price"] = pd.to_numeric(df["price"], errors="coerce").round(2)
    df["category"] = (df["category"].astype(str).str.strip().str.lower()
                      .map(CATEGORY_CANON))
    df["sku"] = df["sku"].astype(str).str.strip()
    return df.reset_index(drop=True)


def clean_orders(raw: pd.DataFrame, customers: pd.DataFrame,
                 products: pd.DataFrame, store: dict) -> pd.DataFrame:
    df = raw.copy()
    df = quarantine(df, df.duplicated(keep="first"), "exact_duplicate_row",
                    store)
    df = quarantine(df, df.duplicated(subset=["order_id"], keep="first"),
                    "duplicate_order_id", store)
    # referential integrity: customer and product must exist (cleaned sets)
    df = quarantine(df, ~df["customer_id"].isin(set(customers["customer_id"])),
                    "orphan_customer_id", store)
    df = quarantine(df, ~df["product_id"].isin(set(products["product_id"])),
                    "orphan_product_id", store)
    amount = pd.to_numeric(df["amount"], errors="coerce")
    df = quarantine(df, amount.isna() | (amount <= 0),
                    "missing_or_nonpositive_amount", store)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").round(2)
    qty = pd.to_numeric(df["quantity"], errors="coerce")
    df = quarantine(df, qty.isna() | (qty <= 0),
                    "missing_or_nonpositive_quantity", store)
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").astype(int)
    parsed = parse_dates(df["order_date"])
    df = quarantine(df, parsed.isna(), "missing_or_bad_order_date", store)
    df["order_date"] = parsed.dt.date.astype(str)
    # order cannot predate the customer's signup
    signup = dict(zip(customers["customer_id"],
                      pd.to_datetime(customers["signup_date"]).dt.date))
    od = pd.to_datetime(df["order_date"]).dt.date
    before = od < df["customer_id"].map(signup)
    df = quarantine(df, before, "order_before_signup", store)
    # status must be a known value after normalising case/whitespace
    # ("unknown_status" is not a status — quarantine, don't guess)
    status_norm = df["status"].astype(str).str.strip().str.lower()
    df = quarantine(df, ~status_norm.isin(VALID_STATUS), "invalid_status",
                    store)
    # standardise status
    df["status"] = df["status"].astype(str).str.strip().str.lower()
    return df.reset_index(drop=True)


def profile_counts(raw_c, raw_o, raw_p, clean_c, clean_o, clean_p) -> dict:
    """Per-dimension quality scores, before vs after (fractions 0..1)."""
    def completeness(frames):
        cells = sum(f.size for f in frames)
        nulls = sum(int(f.isna().sum().sum()) for f in frames)
        return 1 - nulls / cells

    def validity(raw_c, raw_o, raw_p):
        checks, bad = 0, 0
        checks += len(raw_c); bad += int((~raw_c["email"].map(is_email)
                                          | raw_c["email"].isna()).sum())
        checks += len(raw_c)
        bad += int(parse_dates(raw_c["signup_date"]).isna().sum())
        age = pd.to_numeric(raw_c["age"], errors="coerce")
        checks += len(raw_c)
        bad += int((age.isna() | (age < 1) | (age > 120)).sum())
        amt = pd.to_numeric(raw_o["amount"], errors="coerce")
        checks += len(raw_o); bad += int((amt.isna() | (amt <= 0)).sum())
        qty = pd.to_numeric(raw_o["quantity"], errors="coerce")
        checks += len(raw_o); bad += int((qty.isna() | (qty <= 0)).sum())
        checks += len(raw_o)
        bad += int(parse_dates(raw_o["order_date"]).isna().sum())
        pr = pd.to_numeric(raw_p["price"], errors="coerce")
        checks += len(raw_p); bad += int((pr.isna() | (pr <= 0)).sum())
        return 1 - bad / checks

    def uniqueness(frames, keys):
        total, dup = 0, 0
        for f, k in zip(frames, keys):
            total += len(f)
            dup_mask = (f.duplicated(subset=[k], keep="first")
                        | f.duplicated(keep="first"))
            dup += int(dup_mask.sum())
        return 1 - dup / total

    def consistency(raw_c, raw_o, raw_p):
        # Fraction of enum values ALREADY in canonical form in the raw
        # data — compared exactly (no lower-casing or mapping first), so
        # "USA"/"usa"/"U.S.A." and "SHIPPED"/"Shipped " count as
        # inconsistent even though they are mappable.
        checks, bad = 0, 0
        checks += len(raw_c)
        bad += int((~raw_c["country"].astype(str).str.strip()
                    .isin({"US", "CA", "GB", "AU", "DE"})).sum())
        checks += len(raw_o)
        bad += int((~raw_o["status"].astype(str).str.strip()
                    .isin(VALID_STATUS)).sum())
        checks += len(raw_p)
        bad += int((~raw_p["category"].astype(str).str.strip()
                    .isin({"Electronics", "Home & Garden", "Clothing",
                           "Sports", "Books"})).sum())
        return 1 - bad / checks

    def referential(raw_o, clean_c, clean_p):
        checks = len(raw_o)
        bad = int((~raw_o["customer_id"].isin(set(clean_c["customer_id"]))).sum())
        bad += int((~raw_o["product_id"].isin(set(clean_p["product_id"]))).sum())
        return 1 - bad / (2 * checks)

    before = {
        "completeness": completeness([raw_c, raw_o, raw_p]),
        "validity": validity(raw_c, raw_o, raw_p),
        "uniqueness": uniqueness([raw_c, raw_o, raw_p],
                                 ["customer_id", "order_id", "product_id"]),
        "consistency": consistency(raw_c, raw_o, raw_p),
        "referential_integrity": referential(raw_o, raw_c, raw_p),
    }
    after = {
        "completeness": completeness([clean_c, clean_o, clean_p]),
        "validity": 1.0,
        "uniqueness": 1.0,
        "consistency": 1.0,
        "referential_integrity": 1.0,
    }
    # the "after = 1.0" values are not assumed: the SQL gate below verifies
    # them; if any check fails the run exits non-zero before writing results.
    before["overall"] = sum(before.values()) / len(before)
    after["overall"] = sum(after.values()) / len(after)
    return {"before": before, "after": after}


def run_sql_gate(db_path: Path, sql_path: Path) -> list[dict]:
    lines = [ln for ln in sql_path.read_text().splitlines()
             if not ln.strip().startswith("--")]
    sql = "\n".join(lines)
    con = sqlite3.connect(db_path)
    results = []
    for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
        cur = con.execute(stmt)
        row = cur.fetchone()
        results.append({"check": row[0], "violations": int(row[1])})
    con.close()
    return results


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    raw_c = pd.read_csv(DATA / "customers_raw.csv")
    raw_o = pd.read_csv(DATA / "orders_raw.csv")
    raw_p = pd.read_csv(DATA / "products_raw.csv")

    store: dict[str, list[pd.DataFrame]] = {}
    clean_c = clean_customers(raw_c, store)
    clean_p = clean_products(raw_p, store)
    clean_o = clean_orders(raw_o, clean_c, clean_p, store)

    # quarantine files (auditable: every dropped row + reason)
    q_frames = [pd.concat(v, ignore_index=True) for v in store.values() if v]
    quarantine_all = (pd.concat(q_frames, ignore_index=True)
                      if q_frames else pd.DataFrame())
    quarantine_all.to_csv(DATA / "quarantine.csv", index=False)

    # cleaned outputs
    clean_c.to_csv(DATA / "customers_clean.csv", index=False)
    clean_o.to_csv(DATA / "orders_clean.csv", index=False)
    clean_p.to_csv(DATA / "products_clean.csv", index=False)

    # SQLite: cleaned tables + SQL validation gate
    db_path = DATA / "ecommerce.sqlite"
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    clean_c.to_sql("customers", con, index=False)
    clean_o.to_sql("orders", con, index=False)
    clean_p.to_sql("products", con, index=False)
    con.close()
    gate = run_sql_gate(db_path, SQL / "validate.sql")
    failed = [g for g in gate if g["violations"] != 0]
    if failed:
        raise SystemExit(f"SQL VALIDATION GATE FAILED: {failed}")

    # quarantine reasons breakdown
    reasons = {}
    if len(quarantine_all):
        reasons = (quarantine_all["quarantine_reason"].value_counts()
                   .to_dict())

    scores = profile_counts(raw_c, raw_o, raw_p, clean_c, clean_o, clean_p)

    report = {
        "raw_rows": {"customers": len(raw_c), "orders": len(raw_o),
                     "products": len(raw_p)},
        "clean_rows": {"customers": len(clean_c), "orders": len(clean_o),
                       "products": len(clean_p)},
        "quarantined_rows": {"customers": len(raw_c) - len(clean_c),
                             "orders": len(raw_o) - len(clean_o),
                             "products": len(raw_p) - len(clean_p)},
        "quarantine_reasons": reasons,
        "quality_scores": scores,
        "sql_validation_gate": gate,
        "total_quarantined": int(len(quarantine_all)),
        "retention_pct": {
            "customers": round(100 * len(clean_c) / len(raw_c), 2),
            "orders": round(100 * len(clean_o) / len(raw_o), 2),
            "products": round(100 * len(clean_p) / len(raw_p), 2),
        },
    }
    (RESULTS / "quality_report.json").write_text(json.dumps(report, indent=2))

    b, a = scores["before"], scores["after"]
    md = ["# Data-quality report (real pipeline run)",
          "",
          f"Raw rows: {len(raw_c):,} customers, {len(raw_o):,} orders, "
          f"{len(raw_p):,} products. Clean rows kept: {len(clean_c):,} / "
          f"{len(clean_o):,} / {len(clean_p):,}. "
          f"Quarantined: {len(quarantine_all):,} rows "
          f"({100 * len(quarantine_all) / (len(raw_c) + len(raw_o) + len(raw_p)):.1f}% "
          "of all raw rows) — every one listed in `data/quarantine.csv` "
          "with its reason; nothing was silently dropped or imputed.",
          "",
          "## Quality scorecard (fraction of checks passing)",
          "",
          "| Dimension | Before | After |",
          "|---|---:|---:|",
          ]
    for dim in ["completeness", "validity", "uniqueness", "consistency",
                "referential_integrity", "overall"]:
        md.append(f"| {dim.replace('_', ' ').title()} | {b[dim]:.4f} "
                  f"| {a[dim]:.4f} |")
    md += ["",
           "## Quarantine reasons",
           "",
           "| Reason | Rows |",
           "|---|---:|"]
    for reason, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        md.append(f"| {reason} | {n} |")
    md += ["",
           "## SQL validation gate",
           "",
           "Every check in `sql/validate.sql` returns 0 violations on the "
           "cleaned tables loaded in `data/ecommerce.sqlite`:",
           "",
           "| Check | Violations |",
           "|---|---:|"]
    for g in gate:
        md.append(f"| {g['check']} | {g['violations']} |")
    md.append("")
    (RESULTS / "quality_report.md").write_text("\n".join(md))

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

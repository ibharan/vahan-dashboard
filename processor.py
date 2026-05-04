"""
Data Processor
Cleans and transforms raw VAHAN scraped data into analysis-ready format.
"""

import pandas as pd
import numpy as np
import logging
from pathlib import Path
from datetime import datetime
import yaml

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    filename="logs/processor.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

with open("config.yaml") as f:
    CFG = yaml.safe_load(f)

RAW_FILE = CFG["data"]["raw_file"]
PROCESSED_FILE = CFG["data"]["processed_file"]

MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# VAHAN 2-wheeler category codes
TWO_WHEELER_CODES = {"2WN", "2WD", "2W", "TWO WHEELER", "MOTOR CYCLE", "SCOOTER", "MOPED"}


def clean_number(val) -> float:
    if pd.isna(val):
        return np.nan
    cleaned = str(val).replace(",", "").replace(" ", "").strip()
    try:
        return float(cleaned) if cleaned else np.nan
    except ValueError:
        return np.nan


def is_two_wheeler(category: str) -> bool:
    if not category:
        return False
    cat_upper = str(category).upper().strip()
    return any(code in cat_upper for code in TWO_WHEELER_CODES)


def process(raw_path: str = RAW_FILE, out_path: str = PROCESSED_FILE) -> pd.DataFrame:
    if not Path(raw_path).exists():
        log.warning(f"Raw file not found: {raw_path}")
        print(f"[WARN] Raw file not found: {raw_path}. Run scraper first.")
        return pd.DataFrame()

    df = pd.read_csv(raw_path)
    log.info(f"Loaded {len(df)} raw rows from {raw_path}")

    # Normalize column names
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # Identify the vehicle category column
    cat_col = next((c for c in df.columns if "vehicle" in c and "category" in c), None)
    if cat_col is None:
        cat_col = next((c for c in df.columns if "category" in c), None)

    # Identify month and count columns
    # VAHAN table is typically wide: Vehicle Category | Jan | Feb | ... | Total
    meta_cols = {"_year", "_month", "_state", "_scraped_at", "scraped_year",
                 "scraped_month", "state_filter", "scrape_timestamp"}
    if cat_col:
        meta_cols.add(cat_col)

    month_cols = [
        c for c in df.columns
        if c.lower().rstrip("_0123456789") in MONTH_MAP and c not in meta_cols
    ]
    total_cols = [c for c in df.columns if "total" in c and c not in meta_cols]

    # Prefer month columns for granularity; fall back to total
    value_cols = month_cols if month_cols else total_cols

    id_vars = [c for c in df.columns if c in meta_cols or c == cat_col]
    id_vars = list(dict.fromkeys(id_vars))  # deduplicate, preserve order

    if value_cols:
        df_long = df.melt(
            id_vars=[c for c in id_vars if c in df.columns],
            value_vars=[c for c in value_cols if c in df.columns],
            var_name="month_col",
            value_name="registrations_raw",
        )
        # Map month column name → month number
        df_long["month_num"] = df_long["month_col"].str.lower().str.rstrip("_0123456789").map(MONTH_MAP)
    else:
        df_long = df.copy()
        df_long["month_col"] = df_long.get("_month", "")
        df_long["month_num"] = df_long["month_col"].str.lower().map(MONTH_MAP)
        df_long["registrations_raw"] = df_long.get(
            next((c for c in df.columns if c not in meta_cols and c != cat_col), None), np.nan
        )

    # Clean numeric
    df_long["registrations"] = df_long["registrations_raw"].apply(clean_number)

    # Build date: year from _year col, month from month_num
    year_col = "_year" if "_year" in df_long.columns else "scraped_year"
    df_long["year_val"] = pd.to_numeric(df_long.get(year_col, datetime.now().year), errors="coerce").fillna(datetime.now().year).astype(int)

    def make_date(row):
        try:
            m = int(row["month_num"]) if not pd.isna(row["month_num"]) else None
            y = int(row["year_val"])
            if m:
                return pd.Timestamp(year=y, month=m, day=1)
        except Exception:
            pass
        return pd.NaT

    df_long["date"] = df_long.apply(make_date, axis=1)

    # Filter 2-wheelers
    if cat_col and cat_col in df_long.columns:
        df_2w = df_long[df_long[cat_col].apply(is_two_wheeler)].copy()
    else:
        df_2w = df_long.copy()

    # Drop zero / null registrations
    df_2w = df_2w.dropna(subset=["registrations", "date"])
    df_2w = df_2w[df_2w["registrations"] > 0]

    # ── Deduplicate: same date + state + category can appear multiple times ──
    # Keep the max value per group (avoids summing duplicates from multi-table scrape)
    group_cols = [c for c in ["date", "state", "vehicle_category"] if c in df_2w.columns]
    if group_cols:
        df_2w = (df_2w.groupby(group_cols, as_index=False)["registrations"]
                 .max())  # max avoids double-counting duplicates

    # Rename columns
    state_col = "_state" if "_state" in df_2w.columns else "state_filter"
    rename_map = {
        cat_col: "vehicle_category",
        state_col: "state",
        "registrations": "offline_registrations",
    }
    df_final = df_2w.rename(columns={k: v for k, v in rename_map.items() if k in df_2w.columns})

    keep = ["date", "state", "vehicle_category", "offline_registrations"]
    keep = [c for c in keep if c in df_final.columns]
    df_final = df_final[keep].sort_values("date").reset_index(drop=True)

    # Derived columns
    df_final["year"] = df_final["date"].dt.year
    df_final["month"] = df_final["date"].dt.month
    df_final["month_name"] = df_final["date"].dt.strftime("%b %Y")
    # Daily average: monthly registrations / 26 working days
    df_final["daily_avg_offline"] = (df_final["offline_registrations"] / 26).round(0).astype(int)

    # ── Aggregate to monthly totals (sum NT + T + Invalid Carriage) ───────
    agg_cols = [c for c in ["date", "state", "year", "month", "month_name"] if c in df_final.columns]
    df_monthly = (df_final.groupby(agg_cols, as_index=False)["offline_registrations"]
                  .sum())
    df_monthly["daily_avg_offline"] = (df_monthly["offline_registrations"] / 26).round(0).astype(int)
    df_monthly["vehicle_category"] = "TWO WHEELER (ALL)"
    df_final = df_monthly

    Path(out_path).parent.mkdir(exist_ok=True)
    df_final.to_csv(out_path, index=False)
    log.info(f"Processed {len(df_final)} rows → {out_path}")
    print(f"[OK] Processed {len(df_final)} rows → {out_path}")
    return df_final


def generate_sample_data() -> pd.DataFrame:
    """
    Realistic sample data for dashboard demo when VAHAN scrape hasn't run yet.
    Mirrors actual VAHAN 2-wheeler registration volumes (2024-2025).
    """
    import random
    random.seed(42)

    states = [
        "Uttar Pradesh", "Maharashtra", "Tamil Nadu", "Karnataka",
        "Rajasthan", "Gujarat", "Madhya Pradesh", "Andhra Pradesh",
        "West Bengal", "Telangana", "Bihar", "Haryana",
    ]
    # Base monthly registrations per state (realistic figures)
    base_reg = {
        "Uttar Pradesh": 185000, "Maharashtra": 125000, "Tamil Nadu": 115000,
        "Karnataka": 98000, "Rajasthan": 88000, "Gujarat": 82000,
        "Madhya Pradesh": 76000, "Andhra Pradesh": 72000,
        "West Bengal": 67000, "Telangana": 62000,
        "Bihar": 58000, "Haryana": 54000,
    }
    # Cover from Apr 2024 up to current month
    today = datetime.now()
    total_months = (today.year - 2024) * 12 + today.month - 4 + 1
    total_months = max(total_months, 13)
    months = pd.date_range("2024-04-01", periods=total_months, freq="MS")

    rows = []
    for month in months:
        for state in states:
            # Seasonal variation: Q3 (Oct-Dec) peaks, Q1 (Apr-Jun) dips
            seasonal = 1.15 if month.month in (10, 11, 12) else (0.90 if month.month in (4, 5, 6) else 1.0)
            reg = int(base_reg[state] * seasonal * random.uniform(0.92, 1.08))
            rows.append({
                "date": month,
                "state": state,
                "vehicle_category": "2WN",
                "offline_registrations": reg,
                "year": month.year,
                "month": month.month,
                "month_name": month.strftime("%b %Y"),
                "daily_avg_offline": round(reg / 26),
            })

    df = pd.DataFrame(rows)
    Path(PROCESSED_FILE).parent.mkdir(exist_ok=True)
    df.to_csv(PROCESSED_FILE, index=False)
    print(f"[OK] Sample data generated → {PROCESSED_FILE}")
    return df


if __name__ == "__main__":
    df = process()
    if df.empty:
        print("Generating sample data for demo...")
        df = generate_sample_data()
    print(df.tail(10))

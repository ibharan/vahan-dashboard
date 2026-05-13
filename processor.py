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

    # ── DEDUP: keep only the latest scrape run per _year ─────────────────
    if "_scraped_at" in df.columns and "_year" in df.columns:
        df["_scraped_at"] = pd.to_datetime(df["_scraped_at"], errors="coerce")
        df["_scrape_run"] = df["_scraped_at"].dt.floor("min")
        latest_run_per_year = df.groupby("_year")["_scrape_run"].transform("max")
        df = df[df["_scrape_run"] == latest_run_per_year].copy()
        log.info(f"After dedup (latest scrape per year): {len(df)} rows")
        print(f"[INFO] Using latest scrape per year: {len(df)} rows")

    # ── Filter to 2-wheeler rows only ────────────────────────────────────
    cat_col = next((c for c in df.columns if "vehicle" in c and "category" in c), None)
    if cat_col and cat_col in df.columns:
        df = df[df[cat_col].apply(is_two_wheeler)].copy()
        print(f"[INFO] 2-wheeler rows: {len(df)}")

    # ── Identify pure month columns (jan-dec), exclude total & meta ──────
    # The raw CSV has columns like: jan, feb, mar, apr, _year, _state, _scraped_at, may, jun...
    # We must exclude: s_no, vehicle_category, month_wise, total, and all _ prefixed cols
    MONTH_NAMES = {"jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"}
    NON_DATA_COLS = {"s_no", "month_wise", "total", "_year", "_state", "_scraped_at",
                     "_scrape_run", cat_col}

    month_cols = [c for c in df.columns
                  if c.lower() in MONTH_NAMES and c not in NON_DATA_COLS]
    print(f"[INFO] Month columns found: {month_cols}")

    if not month_cols:
        print("[WARN] No month columns found in raw data")
        return pd.DataFrame()

    # ── Process each year separately to handle column layout differences ──
    # NOTE: Due to a scraper column-shift bug, 2026 data is offset:
    # 'Month Wise' = Jan, 'TOTAL' = Feb, 'JAN' = Mar, 'FEB' = Apr, 'MAR' = May, 'APR' = YTD Total
    # For 2025, columns are correct: JAN=Jan, FEB=Feb, ... NOV=YTD Total

    # Define correct month sequence per year based on observed data
    CORRECT_2025_COLS = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct"]  # nov = YTD total, skip
    CORRECT_2026_COLS_MAP = {
        "month_wise": 1,  # Jan
        "total":      2,  # Feb
        "jan":        3,  # Mar
        "feb":        4,  # Apr
        "mar":        5,  # May
        # "apr" = YTD total, skip
    }

    all_rows = []

    # ── 2025: standard columns jan-oct (nov is YTD total) ────────────────
    grp2025 = df[df["_year"] == 2025]
    for _, row in grp2025.iterrows():
        for mc in CORRECT_2025_COLS:
            if mc not in df.columns:
                continue
            val = clean_number(row.get(mc))
            if pd.isna(val) or val <= 0:
                continue
            month_num = MONTH_MAP.get(mc)
            if not month_num:
                continue
            all_rows.append({"date": pd.Timestamp(year=2025, month=month_num, day=1),
                              "registrations": val})

    # ── 2026: columns are shifted — use explicit mapping ─────────────────
    # Due to scraper offset, actual month data is in these columns:
    # month_wise=Jan, total=Feb, jan=Mar, feb=Apr, mar=May (apr=YTD total, skip)
    grp2026 = df[df["_year"] == 2026]
    CORRECT_2026_COLS_MAP = {
        "month_wise": 1,  # Jan 2026
        "total":      2,  # Feb 2026
        "jan":        3,  # Mar 2026
        "feb":        4,  # Apr 2026
        "mar":        5,  # May 2026
        # "apr" = YTD total, skip
    }
    for _, row in grp2026.iterrows():
        for col, month_num in CORRECT_2026_COLS_MAP.items():
            val = clean_number(row.get(col))
            if pd.isna(val) or val <= 0:
                continue
            all_rows.append({"date": pd.Timestamp(year=2026, month=month_num, day=1),
                              "registrations": val})

    if not all_rows:
        print("[WARN] No valid rows after processing")
        return pd.DataFrame()

    df_long = pd.DataFrame(all_rows)

    # ── Aggregate: sum all 2-wheeler sub-categories per month ────────────
    df_monthly = df_long.groupby("date", as_index=False)["registrations"].sum()
    df_monthly = df_monthly.rename(columns={"registrations": "offline_registrations"})

    # Derived columns
    df_monthly["year"]              = df_monthly["date"].dt.year
    df_monthly["month"]             = df_monthly["date"].dt.month
    df_monthly["month_name"]        = df_monthly["date"].dt.strftime("%b %Y")
    df_monthly["daily_avg_offline"] = (df_monthly["offline_registrations"] / 26).round(0).astype(int)
    df_monthly["vehicle_category"]  = "TWO WHEELER (ALL)"

    df_final = df_monthly.sort_values("date").reset_index(drop=True)

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

"""
run_pipeline.py — One-command entry point
Usage:
  python run_pipeline.py          # scrape + process
  python run_pipeline.py --demo   # generate sample data only (no browser needed)
  python run_pipeline.py --dash   # launch dashboard after pipeline
"""

import sys
import subprocess
from pathlib import Path


def main():
    demo_mode = "--demo" in sys.argv
    launch_dash = "--dash" in sys.argv

    # Ensure we're running from the right directory
    script_dir = Path(__file__).parent
    import os
    os.chdir(script_dir)

    Path("data").mkdir(exist_ok=True)
    Path("logs").mkdir(exist_ok=True)

    if demo_mode:
        print("[DEMO] Generating sample data (no browser scraping)...")
        from processor import generate_sample_data
        df = generate_sample_data()
        print(f"[OK] Sample data ready: {len(df)} rows")
    else:
        print("[1/2] Running scraper...")
        from scraper import scrape_vahan, save_raw
        df_raw = scrape_vahan()
        if not df_raw.empty:
            save_raw(df_raw)
        else:
            print("[WARN] Scraper returned no data — generating sample data for demo")
            from processor import generate_sample_data
            generate_sample_data()

        print("[2/2] Processing data...")
        from processor import process
        df = process()
        if df.empty:
            from processor import generate_sample_data
            generate_sample_data()

    if launch_dash:
        print("\nLaunching dashboard at http://localhost:8501 ...")
        subprocess.run(["streamlit", "run", "dashboard.py"])


if __name__ == "__main__":
    main()

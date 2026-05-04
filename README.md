# VAHAN 2-Wheeler Sales Dashboard
**Amazon Automotive GL — Offline (VAHAN) vs Online (Amazon) Comparison**

---

## Architecture

```
VAHAN Portal (MoRTH)
       │
       ▼
  scraper.py          ← Selenium scrapes 2W registrations daily
       │
       ▼
  data/vahan_raw.csv
       │
       ▼
  processor.py        ← Cleans, filters 2W, computes daily avg
       │
       ▼
  data/vahan_processed.csv
       │
       ▼
  dashboard.py        ← Streamlit: offline vs Amazon online comparison
       ▲
  data/amazon_online_sales.csv  ← Drop your internal export here
```

**Automation:** `scheduler.py` + Windows Task Scheduler runs the full pipeline daily at 8 AM IST.

---

## Quick Start

### 1. Install dependencies
```bash
cd vahan_dashboard
pip install -r requirements.txt
```

### 2. Run the pipeline (first time)
```bash
# Option A: Full scrape (requires Chrome)
python run_pipeline.py

# Option B: Demo mode — no browser, uses realistic sample data
python run_pipeline.py --demo

# Option C: Scrape + launch dashboard in one command
python run_pipeline.py --dash
```

### 3. Launch the dashboard
```bash
streamlit run dashboard.py
```
Opens at **http://localhost:8501**

### 4. Set up daily automation (Windows)
Run PowerShell as Administrator:
```powershell
.\setup_task_scheduler.ps1
```
This registers a Windows Task Scheduler job that runs the pipeline every day at 8 AM IST.

---

## Connecting Your Amazon Online Sales Data

Drop a CSV at `data/amazon_online_sales.csv` with these columns:

| Column | Type | Example |
|--------|------|---------|
| `date` | YYYY-MM-DD | 2024-04-01 |
| `amazon_online_units` | integer | 52000 |

The dashboard auto-detects this file. Until it exists, realistic demo data is shown.

---

## Project Structure
```
vahan_dashboard/
├── scraper.py              # Selenium scraper for VAHAN portal
├── processor.py            # Data cleaning & transformation
├── dashboard.py            # Streamlit dashboard
├── scheduler.py            # APScheduler daily automation
├── run_pipeline.py         # One-command entry point
├── setup_task_scheduler.ps1 # Windows Task Scheduler setup
├── config.yaml             # All configuration
├── requirements.txt
├── data/
│   ├── vahan_raw.csv           # Raw scraped data (auto-created)
│   ├── vahan_processed.csv     # Clean analysis-ready data (auto-created)
│   └── amazon_online_sales.csv # Your internal Amazon data (you provide)
└── logs/
    ├── scraper.log
    ├── processor.log
    └── scheduler.log
```

---

## Dashboard Features
| Chart | What it shows |
|-------|--------------|
| KPI cards | Total offline, latest month, daily avg, Amazon units, market share % |
| Monthly bar chart | Offline 2W registrations trend |
| Top states | Horizontal bar — top 10 states by volume |
| Offline vs Online | Grouped bar — VAHAN vs Amazon side-by-side |
| Market share pie | Amazon online % of total market |
| Daily avg trend | Month-over-month daily average line chart |
| YoY growth | Year-over-year % change (needs 2+ years selected) |
| State × Month heatmap | Registration intensity across states and months |
| Raw data table | Filterable table with CSV export |

---

## Configuration (`config.yaml`)
```yaml
vahan:
  states: []          # Empty = All India aggregate; add state names for granular data
  headless: true      # Set false to watch the browser (debug mode)

scheduler:
  hour: 8             # Run at 8 AM IST
  minute: 0
```

---

## Notes
- VAHAN portal uses PrimeFaces JSF — Selenium is required (no simple HTTP scraping)
- Data covers RTOs on VAHAN 4.0 (~95% of India)
- Daily avg = monthly registrations ÷ 26 working days
- Set `headless: false` in `config.yaml` to debug scraping visually
- If scraper fails (portal down / UI change), the pipeline falls back to existing data

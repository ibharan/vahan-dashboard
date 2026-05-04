"""
VAHAN Portal Scraper — Direct hidden-select approach
Sets PrimeFaces dropdown values by writing to the hidden <select> _input element
and firing the onchange event. This is the most reliable method.

Verified IDs from live page (2026-04-30):
  j_idt29  = Unit (In Thousand / In Lakh / In Crore / Actual Value)
  j_idt39  = State
  selectedRto = RTO
  yaxisVar = Y-Axis
  xaxisVar = X-Axis
  selectedYearType = Year Type (Select / Financial Year / Calendar Year)
  selectedYear = Year
  vchgroupTable:selectCatgGrp = Category Group
"""

import time
import logging
import pandas as pd
from datetime import datetime
from pathlib import Path

import yaml
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    filename="logs/scraper.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

with open("config.yaml") as f:
    CFG = yaml.safe_load(f)

VAHAN_URL  = CFG["vahan"]["base_url"]
OUTPUT_RAW = CFG["data"]["raw_file"]


def get_driver(headless: bool = True) -> webdriver.Chrome:
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(CFG["vahan"]["page_load_timeout"])
    return driver


def set_select_by_text(driver, base_id: str, option_text: str) -> bool:
    """
    Set a PrimeFaces SelectOneMenu by directly manipulating the hidden <select>.
    Finds the option whose text matches, sets the select value, fires onchange.
    """
    input_id = base_id + "_input"

    script = f"""
        // Try multiple selector strategies for dynamic JSF IDs
        var sel = document.getElementById('{input_id}');
        if (!sel) {{
            // querySelector with attribute selector handles colons in IDs
            sel = document.querySelector('select[id="{input_id}"]');
        }}
        if (!sel) {{
            // Search all selects by name
            var allSels = document.querySelectorAll('select');
            for (var s = 0; s < allSels.length; s++) {{
                if (allSels[s].id === '{input_id}' || allSels[s].name === '{input_id}') {{
                    sel = allSels[s]; break;
                }}
            }}
        }}
        if (!sel) return 'NO_SELECT:' + '{input_id}';

        var found = false;
        var available = [];
        for (var i = 0; i < sel.options.length; i++) {{
            available.push(sel.options[i].text);
            if (sel.options[i].text.toLowerCase().indexOf('{option_text.lower().replace("'", "\\'")}') >= 0) {{
                sel.selectedIndex = i;
                found = true;
                break;
            }}
        }}
        if (!found) return 'NOT_FOUND:' + available.join('|');

        // Fire the onchange to trigger PrimeFaces AJAX update
        var evt = new Event('change', {{bubbles: true}});
        sel.dispatchEvent(evt);

        // Also update the visible label
        var label = document.getElementById('{base_id}_label');
        if (label) label.textContent = sel.options[sel.selectedIndex].text;

        return 'OK:' + sel.options[sel.selectedIndex].text;
    """
    try:
        result = driver.execute_script(script)
        log.info(f"set_select({base_id}, '{option_text}'): {result}")
        if result and result.startswith("OK:"):
            print(f"  ✓ {base_id} = '{result[3:]}'")
            time.sleep(2)  # wait for AJAX to complete
            return True
        elif result and result.startswith("NOT_FOUND:"):
            available = result[10:].split("|")
            print(f"  [WARN] '{option_text}' not in '{base_id}'. Options: {available}")
            return False
        else:
            print(f"  [WARN] {base_id}: {result}")
            return False
    except Exception as e:
        log.error(f"set_select({base_id}): {e}")
        print(f"  [ERROR] {base_id}: {e}")
        return False


def click_refresh(driver) -> bool:
    xpaths = [
        "//button[contains(translate(normalize-space(.),'REFRESH','refresh'),'refresh')]",
        "//button[contains(@id,'refresh') or contains(@id,'Refresh') or contains(@id,'btnRefresh')]",
        "//input[@value='Refresh' or @value='Search']",
        "//a[contains(translate(normalize-space(.),'REFRESH','refresh'),'refresh')]",
    ]
    for xp in xpaths:
        try:
            btn = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((By.XPATH, xp))
            )
            driver.execute_script("arguments[0].click();", btn)
            log.info("Refresh clicked")
            print("  ✓ Refresh clicked")
            return True
        except Exception:
            pass

    # Last resort: find any button and log them all
    btns = driver.find_elements(By.TAG_NAME, "button")
    print(f"  [DEBUG] All buttons on page: {[b.text or b.get_attribute('id') for b in btns]}")
    log.error("Refresh button not found")
    return False


def extract_table(driver) -> list[dict]:
    records = []
    try:
        # VAHAN uses id="groupingTable" with role="grid"
        WebDriverWait(driver, 40).until(
            EC.presence_of_element_located((By.ID, "groupingTable"))
        )

        # Wait for actual data to populate (VAHAN loads table shell first, then AJAX fills it)
        print("  [INFO] Waiting for table data to load...")
        for attempt in range(20):  # up to 40 more seconds
            try:
                table_el = driver.find_element(By.ID, "groupingTable")
                # The scrollable body has the data rows
                body_rows = driver.find_elements(By.CSS_SELECTOR,
                    "#groupingTable_data tr, .ui-datatable-scrollable-body tr"
                )
                if not body_rows:
                    # Try the scrollable body div
                    body_rows = driver.find_elements(By.XPATH,
                        "//div[contains(@class,'ui-datatable-scrollable-body')]//tr"
                    )

                if body_rows:
                    # Check if cells have actual text
                    first_cells = body_rows[0].find_elements(By.TAG_NAME, "td")
                    if first_cells and any(c.text.strip() for c in first_cells):
                        print(f"  [INFO] Data rows found: {len(body_rows)}")
                        break
            except Exception:
                pass
            time.sleep(2)

        # Extract headers from the header table
        headers = []
        try:
            header_ths = driver.find_elements(By.CSS_SELECTOR,
                "#groupingTable_head th .ui-column-title"
            )
            headers = [th.text.strip() for th in header_ths if th.text.strip()]
        except Exception:
            pass

        if not headers:
            # Fallback: get from thead tr
            try:
                thead_ths = driver.find_elements(By.XPATH,
                    "//thead[@id='groupingTable_head']//th[not(contains(@id,'ghost'))]"
                )
                headers = [th.text.strip() for th in thead_ths if th.text.strip()]
            except Exception:
                pass

        print(f"  [TABLE] Headers: {headers}")
        log.info(f"Headers: {headers}")

        # Extract data rows from scrollable body
        body_rows = driver.find_elements(By.XPATH,
            "//div[contains(@class,'ui-datatable-scrollable-body')]//tr | "
            "//*[@id='groupingTable_data']//tr"
        )

        for row in body_rows:
            cells = [td.text.strip() for td in row.find_elements(By.TAG_NAME, "td")]
            if not cells or all(c == "" for c in cells):
                continue
            if headers:
                records.append(dict(zip(headers, cells)))
            else:
                records.append({"col_" + str(i): v for i, v in enumerate(cells)})

        print(f"  [INFO] Extracted {len(records)} records")

    except TimeoutException:
        print("  [WARN] groupingTable did not appear — saving debug HTML")
        with open("logs/vahan_after_refresh.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        print("  [INFO] Saved → logs/vahan_after_refresh.html")
    except Exception as e:
        log.error(f"extract_table: {e}", exc_info=True)
        print(f"  [ERROR] extract_table: {e}")

    return records


def scrape_vahan(year: int = None, states: list[str] = None) -> pd.DataFrame:
    if year is None:
        year = datetime.now().year
    if states is None:
        states = CFG["vahan"].get("states") or []

    driver = get_driver(headless=CFG["vahan"]["headless"])
    all_records = []

    try:
        print("[INFO] Opening VAHAN portal...")
        driver.get(VAHAN_URL)
        time.sleep(6)
        print(f"[INFO] Page: '{driver.title}'")

        # ── Configure all filters ─────────────────────────────────────────
        print("\n[INFO] Configuring filters...")

        # Y-Axis = Vehicle Category
        set_select_by_text(driver, "yaxisVar", "Vehicle Category")
        time.sleep(2)

        # X-Axis = Month Wise
        set_select_by_text(driver, "xaxisVar", "Month Wise")

        # Category Group = TWO WHEELER
        set_select_by_text(driver, "vchgroupTable:selectCatgGrp", "TWO WHEELER")

        # Year Type = Calendar Year
        for yt in ["Calendar Year", "Select Year", "Select"]:
            if set_select_by_text(driver, "selectedYearType", yt):
                time.sleep(1.5)
                break

        # State = All India (default, already selected)
        state_val = states[0] if states else "All Vahan4 Running States"
        set_select_by_text(driver, "j_idt39", state_val)

        # ── Scrape each year ──────────────────────────────────────────────
        years_to_scrape = CFG["vahan"].get("years") or [year]

        for yr in years_to_scrape:
            print(f"\n[INFO] Scraping year {yr}...")
            set_select_by_text(driver, "selectedYear", str(yr))

            print("[INFO] Clicking Refresh...")
            if not click_refresh(driver):
                print(f"[ERROR] Could not click Refresh for {yr}")
                continue

            time.sleep(12)
            rows = extract_table(driver)
            for r in rows:
                r["_year"]       = yr
                r["_state"]      = state_val
                r["_scraped_at"] = datetime.now().isoformat()
            all_records.extend(rows)
            print(f"  ✓ {len(rows)} rows for {yr}")
            time.sleep(3)

        # ── Scrape additional states if specified ─────────────────────────
        for state in states[1:]:
            print(f"\n[INFO] Scraping state: {state}...")
            set_select_by_text(driver, "j_idt39", state)
            time.sleep(1)
            for yr in years_to_scrape:
                set_select_by_text(driver, "selectedYear", str(yr))
                if click_refresh(driver):
                    time.sleep(8)
                    rows = extract_table(driver)
                    for r in rows:
                        r["_year"]       = yr
                        r["_state"]      = state
                        r["_scraped_at"] = datetime.now().isoformat()
                    all_records.extend(rows)
                    print(f"  ✓ {len(rows)} rows — {state} {yr}")
                time.sleep(2)

    except Exception as e:
        log.error(f"Fatal: {e}", exc_info=True)
        print(f"[ERROR] Fatal: {e}")
        try:
            with open("logs/vahan_fatal.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
        except Exception:
            pass
    finally:
        driver.quit()

    if not all_records:
        return pd.DataFrame()

    df = pd.DataFrame(all_records)
    log.info(f"Total: {len(df)} rows")
    return df


def save_raw(df: pd.DataFrame):
    Path(CFG["data"]["output_dir"]).mkdir(exist_ok=True)
    path = Path(OUTPUT_RAW)
    if path.exists():
        existing = pd.read_csv(path)
        combined = pd.concat([existing, df], ignore_index=True).drop_duplicates()
    else:
        combined = df
    combined.to_csv(path, index=False)
    log.info(f"Saved {len(combined)} records → {OUTPUT_RAW}")
    print(f"[OK] Saved {len(combined)} records → {OUTPUT_RAW}")


if __name__ == "__main__":
    df = scrape_vahan()
    if not df.empty:
        save_raw(df)
        print(df.head())
    else:
        print("[WARN] No data. Check logs/scraper.log")

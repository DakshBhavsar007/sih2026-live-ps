import os
import re
import ssl
import time
import logging
from datetime import datetime, timezone
import urllib.request
from bs4 import BeautifulSoup

logger = logging.getLogger("sih_scraper")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SIH_SOURCE_URL = os.environ.get("SIH_SOURCE_URL", "https://www.sih.gov.in/sih2026PS")
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "300"))
SCRAPE_TIMEOUT_SECONDS = int(os.environ.get("SCRAPE_TIMEOUT_SECONDS", "20"))

# In-memory cache storage
_cache = {
    "data": None,
    "updated_at": None,
    "last_success_timestamp": 0
}

def fetch_sih_html(url=None, timeout=None):
    """
    Fetch the raw HTML from the official SIH 2026 PS portal using a realistic browser User-Agent
    and an SSL context tolerant of government certificate configurations.
    """
    target_url = url or SIH_SOURCE_URL
    req_timeout = timeout or SCRAPE_TIMEOUT_SECONDS

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Connection": "keep-alive"
    }

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(target_url, headers=headers)
    logger.info(f"Fetching official SIH page from: {target_url} (timeout: {req_timeout}s)")
    with urllib.request.urlopen(req, context=ctx, timeout=req_timeout) as resp:
        if resp.status != 200:
            raise RuntimeError(f"SIH server returned HTTP {resp.status}")
        raw_html = resp.read().decode("utf-8", errors="ignore")
        logger.info(f"Successfully fetched {len(raw_html)} bytes from SIH.")
        return raw_html

def parse_sih_html(html_content, fallback_data=None):
    """
    Parse the official SIH HTML robustly:
    - Finds the problem statement table.
    - Dynamically detects the 'Submitted Idea(s) Count' column index.
    - Matches problem statements SIH26001 through SIH26240.
    - Tolerates formatting, extra spaces, and varying capacities.
    - Preserves previous valid count if parsing a specific cell fails.
    """
    if not html_content or not html_content.strip():
        raise ValueError("Empty HTML content received from SIH.")

    soup = BeautifulSoup(html_content, "lxml")
    
    # Try finding table by id or class or content
    main_table = soup.find("table", id="dataTablePS")
    if not main_table:
        for tab in soup.find_all("table"):
            tab_text = tab.get_text()
            if "Submitted Idea" in tab_text and ("PS Number" in tab_text or "SIH26" in tab_text):
                main_table = tab
                break

    if not main_table:
        tables = soup.find_all("table")
        if tables:
            main_table = tables[0]
        else:
            raise ValueError("No table found in official SIH page.")

    # Dynamically find header indices
    header_idx_submitted = -1
    header_idx_ps_id = -1

    for tr in main_table.find_all("tr"):
        ths = tr.find_all("th")
        if ths:
            for idx, th in enumerate(ths):
                h_text = re.sub(r"\s+", " ", th.get_text(strip=True).lower())
                if "submitted" in h_text and ("count" in h_text or "idea" in h_text):
                    header_idx_submitted = idx
                elif "ps number" in h_text or "problem statement id" in h_text or h_text == "id":
                    header_idx_ps_id = idx
            break

    logger.info(f"Dynamic column detection: submitted_col={header_idx_submitted}, ps_id_col={header_idx_ps_id}")

    results = {}
    if fallback_data:
        # Shallow copy of previous counts so we never wipe valid data
        for k, v in fallback_data.items():
            results[k] = dict(v)

    # Process each row
    for tr in main_table.find_all("tr"):
        # Use recursive=False to ignore modal dialog tables nested inside cell descriptions
        tds = tr.find_all("td", recursive=False)
        if not tds:
            continue

        row_text = tr.get_text(" ", strip=True)
        ps_match = re.search(r"\b(SIH26\d{3,4})\b", row_text)
        if not ps_match:
            continue

        ps_id = ps_match.group(1).upper()

        submitted_val = None
        capacity_val = 500
        display_val = None

        # Strategy 1: Check detected submitted column index
        if 0 <= header_idx_submitted < len(tds):
            col_text = tds[header_idx_submitted].get_text(strip=True)
            m = re.search(r"(\d+)\s*/\s*(\d+)", col_text)
            if m:
                submitted_val = int(m.group(1))
                capacity_val = int(m.group(2))
                display_val = f"{submitted_val}/{capacity_val}"
            else:
                m_single = re.search(r"^\s*(\d+)\s*$", col_text)
                if m_single:
                    submitted_val = int(m_single.group(1))
                    display_val = f"{submitted_val}/{capacity_val}"

        # Strategy 2: Fallback scan through all direct tds of the row
        if display_val is None:
            for td in tds:
                col_text = td.get_text(strip=True)
                m = re.search(r"(\d+)\s*/\s*(\d+)", col_text)
                if m:
                    submitted_val = int(m.group(1))
                    capacity_val = int(m.group(2))
                    display_val = f"{submitted_val}/{capacity_val}"
                    break

        if display_val is not None:
            results[ps_id] = {
                "submitted": submitted_val,
                "capacity": capacity_val,
                "display": display_val
            }
        elif ps_id not in results:
            # If completely unparseable and not in previous cache, log warning
            logger.warning(f"Could not parse submission count for {ps_id}")

    if not results:
        raise ValueError("Failed to extract any problem statement submission counts from SIH HTML.")

    logger.info(f"Successfully parsed submission counts for {len(results)} problem statements.")
    return results

def get_live_submissions(force_refresh=False):
    """
    Retrieves live submission counts with:
    - 5-minute TTL caching
    - Graceful degradation if SIH portal is down/slow
    - Forced refresh option for manual 'Sync Now'
    """
    global _cache
    now = time.time()
    iso_now = datetime.now(timezone.utc).isoformat()

    has_cache = _cache["data"] is not None and len(_cache["data"]) > 0
    cache_age = now - _cache["last_success_timestamp"]
    is_cache_fresh = has_cache and (cache_age < CACHE_TTL_SECONDS)

    # Return cached data if fresh and no forced refresh requested
    if is_cache_fresh and not force_refresh:
        return {
            "success": True,
            "source": SIH_SOURCE_URL,
            "updated_at": _cache["updated_at"],
            "cached": True,
            "stale": False,
            "data": _cache["data"]
        }

    # Attempt to fetch fresh data from SIH
    try:
        html = fetch_sih_html()
        new_data = parse_sih_html(html, fallback_data=_cache["data"])
        
        _cache["data"] = new_data
        _cache["updated_at"] = iso_now
        _cache["last_success_timestamp"] = now

        return {
            "success": True,
            "source": SIH_SOURCE_URL,
            "updated_at": iso_now,
            "cached": False,
            "stale": False,
            "data": new_data
        }
    except Exception as e:
        logger.error(f"Error fetching/parsing live SIH data: {e}")
        # If we have existing cached data, return it marked as stale
        if has_cache:
            return {
                "success": True,
                "source": SIH_SOURCE_URL,
                "updated_at": _cache["updated_at"],
                "cached": True,
                "stale": True,
                "warning": "SIH sync unavailable — showing last successful data.",
                "error": str(e),
                "data": _cache["data"]
            }
        else:
            # First fetch failed and no cache exists
            return {
                "success": False,
                "source": SIH_SOURCE_URL,
                "updated_at": None,
                "cached": False,
                "stale": True,
                "error": "Live SIH data unavailable — showing stored dataset.",
                "details": str(e),
                "data": {}
            }

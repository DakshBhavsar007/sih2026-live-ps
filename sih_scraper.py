import os
import re
import ssl
import json
import time
import logging
from datetime import datetime, timezone
import urllib.request
from bs4 import BeautifulSoup

try:
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

logger = logging.getLogger("sih_scraper")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SIH_SOURCE_URL = os.environ.get("SIH_SOURCE_URL", "https://www.sih.gov.in/sih2026PS")
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "300"))
SCRAPE_TIMEOUT_SECONDS = int(os.environ.get("SCRAPE_TIMEOUT_SECONDS", "20"))

def load_baseline_data():
    """Load baseline dataset from sih2026_problem_statements.json so cache is never empty."""
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sih2026_problem_statements.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            items = data.get("problem_statements", [])
            baseline = {}
            for p in items:
                ps_id = p.get("id")
                si = p.get("submitted_ideas")
                if ps_id and si:
                    if isinstance(si, dict):
                        cnt = si.get("count", si.get("submitted", 0))
                        cap = si.get("capacity", 500)
                        disp = si.get("raw", f"{cnt}/{cap}")
                    else:
                        m = re.search(r"(\d+)(?:\s*/\s*(\d+))?", str(si))
                        cnt = int(m.group(1)) if m else 0
                        cap = int(m.group(2)) if m and m.group(2) else 500
                        disp = f"{cnt}/{cap}"
                    baseline[ps_id] = {
                        "submitted": cnt,
                        "capacity": cap,
                        "display": disp
                    }
            logger.info(f"Loaded {len(baseline)} baseline records into cache.")
            return baseline
        except Exception as e:
            logger.warning(f"Could not load baseline dataset: {e}")
    return {}

# Pre-populate in-memory cache with baseline data so cold-start never fails with 503
_cache = {
    "data": load_baseline_data(),
    "updated_at": datetime.now(timezone.utc).isoformat(),
    "last_success_timestamp": time.time(),
    "last_attempt_timestamp": 0
}

def set_cached_submissions(new_data):
    """
    Manually update the submission count cache (e.g., via push sync from client or Indian proxy).
    """
    global _cache
    if not new_data or not isinstance(new_data, dict):
        return False
    now = time.time()
    iso_now = datetime.now(timezone.utc).isoformat()
    _cache["data"] = new_data
    _cache["updated_at"] = iso_now
    _cache["last_success_timestamp"] = now
    _cache["last_attempt_timestamp"] = now
    logger.info(f"Manual cache update succeeded with {len(new_data)} entries.")
    return True

def fetch_sih_html(url=None, timeout=None):
    """
    Fetch raw HTML from the official SIH portal.
    Uses realistic modern browser headers, requests.Session with cookie warmup,
    proxy support (SIH_PROXY / HTTP_PROXY / HTTPS_PROXY), and urllib fallback.
    """
    target_url = url or SIH_SOURCE_URL
    req_timeout = timeout or SCRAPE_TIMEOUT_SECONDS

    # Proxy support if set in environment (e.g., for routing through an Indian proxy)
    proxy_url = os.environ.get("SIH_PROXY") or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    if proxies:
        logger.info(f"Using proxy: {proxy_url}")

    browser_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Dnt": "1",
        "Sec-Ch-Ua": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Referer": "https://www.sih.gov.in/",
        "Connection": "keep-alive"
    }

    # Try requests first
    if HAS_REQUESTS:
        try:
            logger.info(f"Fetching official SIH page via requests: {target_url} (timeout: {req_timeout}s)")
            session = requests.Session()
            session.headers.update(browser_headers)
            if proxies:
                session.proxies.update(proxies)

            # First attempt with standard verification
            r = None
            try:
                r = session.get(target_url, timeout=req_timeout, allow_redirects=True)
            except requests.exceptions.SSLError:
                logger.warning("SSL verification failed, retrying with verify=False...")
                r = session.get(target_url, timeout=req_timeout, verify=False, allow_redirects=True)

            if r and r.status_code == 200 and len(r.text) > 10000:
                logger.info(f"Successfully fetched {len(r.text)} characters from SIH via requests.")
                return r.text

            # If 403 or blocked, try warming session cookies on root portal first
            if r and r.status_code == 403:
                logger.warning(f"Direct access returned 403. Attempting session cookie warmup on homepage...")
                try:
                    session.get("https://www.sih.gov.in/", timeout=10, allow_redirects=True)
                    r = session.get(target_url, timeout=req_timeout, allow_redirects=True)
                    if r.status_code == 200 and len(r.text) > 10000:
                        logger.info(f"Successfully fetched {len(r.text)} characters after cookie warmup.")
                        return r.text
                except Exception as warm_err:
                    logger.warning(f"Homepage warmup failed: {warm_err}")

            if r:
                logger.warning(f"requests returned HTTP {r.status_code}, falling back to urllib.")
        except Exception as err:
            logger.warning(f"requests failed: {err}, falling back to urllib.")

    # Fallback to urllib
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(target_url, headers=browser_headers)
    logger.info(f"Fetching official SIH page via urllib: {target_url} (timeout: {req_timeout}s)")
    with urllib.request.urlopen(req, context=ctx, timeout=req_timeout) as resp:
        if resp.status != 200:
            raise RuntimeError(f"SIH server returned HTTP {resp.status}")
        raw_html = resp.read().decode("utf-8", errors="ignore")
        logger.info(f"Successfully fetched {len(raw_html)} bytes from SIH via urllib.")
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
        for k, v in fallback_data.items():
            results[k] = dict(v)

    # Process each row
    for tr in main_table.find_all("tr"):
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

    if not results:
        raise ValueError("Failed to extract any problem statement submission counts from SIH HTML.")

    logger.info(f"Successfully parsed submission counts for {len(results)} problem statements.")
    return results

def get_live_submissions(force_refresh=False):
    """
    Retrieves live submission counts with:
    - 5-minute TTL caching
    - Pre-populated baseline dataset (never returns empty or 503)
    - Cooldown protection against hammering geo-blocked endpoints
    - Graceful degradation if SIH portal is down/geo-blocked
    - Forced refresh option for manual 'Sync Now'
    """
    global _cache
    now = time.time()
    iso_now = datetime.now(timezone.utc).isoformat()

    has_cache = _cache["data"] is not None and len(_cache["data"]) > 0
    cache_age = now - _cache.get("last_success_timestamp", 0)
    is_cache_fresh = has_cache and (cache_age < CACHE_TTL_SECONDS)

    # Check cooldown after a previous failed attempt (prevents repeated 403 on every page load)
    attempt_age = now - _cache.get("last_attempt_timestamp", 0)
    is_cooling_down = attempt_age < CACHE_TTL_SECONDS

    # Return cached data if fresh or currently in cooldown period
    if has_cache and not force_refresh:
        if is_cache_fresh or is_cooling_down:
            return {
                "success": True,
                "source": SIH_SOURCE_URL,
                "updated_at": _cache["updated_at"],
                "cached": True,
                "stale": not is_cache_fresh,
                "data": _cache["data"]
            }

    # Record this scrape attempt timestamp
    _cache["last_attempt_timestamp"] = now

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
        # If 403, log informative warning explaining NIC firewall geo-blocking
        if "403" in str(e):
            logger.info(f"Official SIH portal geo-blocked cloud IP (HTTP 403 Forbidden). Serving cached baseline dataset. Cooldown: {CACHE_TTL_SECONDS}s.")
        else:
            logger.warning(f"Error fetching/parsing live SIH data: {e}. Serving cached data. Cooldown: {CACHE_TTL_SECONDS}s.")

        fallback = _cache["data"] or load_baseline_data()
        return {
            "success": True,
            "source": SIH_SOURCE_URL,
            "updated_at": _cache["updated_at"] or iso_now,
            "cached": True,
            "stale": True,
            "warning": "SIH live sync currently geo-blocked on cloud datacenter — serving cached data.",
            "error": str(e),
            "data": fallback
        }

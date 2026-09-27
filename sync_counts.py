"""
SIH 2026 Problem Statements — Push Sync Utility
-----------------------------------------------
Scrapes the live submission counts from the official SIH portal:
https://www.sih.gov.in/sih2026PS

And instantly syncs the updated counts to:
1. Local sih2026_problem_statements.json
2. Deployed Render service: https://sih2026-live-ps.onrender.com/api/sih/sync

Usage:
    python sync_counts.py
    python sync_counts.py --render-only
    python sync_counts.py --url https://your-custom-domain.com
"""

import sys
import os
import json
import argparse
import logging
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("Error: 'requests' library is required. Run: pip install requests")
    sys.exit(1)

from sih_scraper import fetch_sih_html, parse_sih_html

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sih_sync")

DEFAULT_RENDER_URL = os.environ.get("RENDER_APP_URL", "https://sih2026-live-ps.onrender.com")

def sync():
    parser = argparse.ArgumentParser(description="Sync live SIH 2026 submission counts.")
    parser.add_argument("--url", default=DEFAULT_RENDER_URL, help="Target backend URL")
    parser.add_argument("--local-only", action="store_true", help="Only update local JSON without pushing to Render")
    parser.add_argument("--secret", default=os.environ.get("SYNC_SECRET", ""), help="Sync secret token if configured")
    args = parser.parse_args()

    logger.info("Fetching latest live submission counts from official SIH portal...")
    try:
        html = fetch_sih_html()
        live_data = parse_sih_html(html)
        logger.info(f"Successfully scraped live counts for {len(live_data)} problem statements!")
    except Exception as e:
        logger.error(f"Failed to fetch live data from SIH portal: {e}")
        sys.exit(1)

    # 1. Update local JSON
    base_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(base_dir, "sih2026_problem_statements.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            updated = 0
            for ps in data.get("problem_statements", []):
                pid = ps.get("id")
                if pid in live_data:
                    ps["submitted_ideas"] = {
                        "count": live_data[pid]["submitted"],
                        "capacity": live_data[pid]["capacity"],
                        "raw": live_data[pid]["display"]
                    }
                    updated += 1
            data["last_updated"] = datetime.now(timezone.utc).isoformat()
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Updated {updated} records in local '{os.path.basename(json_path)}'.")
        except Exception as e:
            logger.warning(f"Could not update local JSON: {e}")

    if args.local_only:
        logger.info("Local sync completed. Skipping cloud push.")
        return

    # 2. Push to Render
    sync_url = f"{args.url.rstrip('/')}/api/sih/sync"
    logger.info(f"Pushing live counts to cloud endpoint: {sync_url} ...")
    headers = {"Content-Type": "application/json"}
    if args.secret:
        headers["X-Sync-Token"] = args.secret

    try:
        resp = requests.post(sync_url, json={"data": live_data}, headers=headers, timeout=15)
        if resp.status_code == 200:
            logger.info(f"SUCCESS! Render live cache updated: {resp.json().get('message')}")
        else:
            logger.warning(f"Cloud push returned HTTP {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.warning(f"Could not push to {sync_url}: {e}")

if __name__ == "__main__":
    sync()

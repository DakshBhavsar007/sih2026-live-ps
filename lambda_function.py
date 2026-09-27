"""
AWS Lambda Auto-Sync Handler (Mumbai Region: ap-south-1)
--------------------------------------------------------
Runs 100% on Python standard library (no pip install or zip packaging required).
Scrapes official SIH portal and pushes live submission counts to Render.
"""

import urllib.request
import ssl
import json
import re

SIH_URL = "https://www.sih.gov.in/sih2026PS"
RENDER_SYNC_URL = "https://sih2026-live-ps.onrender.com/api/sih/sync"

def lambda_handler(event, context):
    print("Fetching live data from official SIH portal from Mumbai IP...")

    # 1. Fetch official SIH HTML using standard library
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,hi;q=0.8"
    }

    req = urllib.request.Request(SIH_URL, headers=headers)
    with urllib.request.urlopen(req, context=ctx, timeout=25) as resp:
        html = resp.read().decode("utf-8", errors="ignore")

    # 2. Extract all 240 problem statements via regex pattern
    matches = re.findall(r'<td>\s*(SIH26\d{3,4})\s*</td>\s*<td>\s*(\d+)\s*/\s*(\d+)\s*</td>', html, re.IGNORECASE)

    data = {}
    for ps_id, sub, cap in matches:
        sub_int = int(sub)
        cap_int = int(cap)
        data[ps_id.upper()] = {
            "submitted": sub_int,
            "capacity": cap_int,
            "display": f"{sub_int}/{cap_int}"
        }

    print(f"Successfully extracted {len(data)} problem statements!")
    if len(data) == 0:
        raise ValueError("No problem statements extracted from SIH HTML.")

    # 3. Push to Render sync endpoint
    payload = json.dumps({"data": data}).encode("utf-8")
    post_req = urllib.request.Request(
        RENDER_SYNC_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(post_req, timeout=15) as post_resp:
        result_body = post_resp.read().decode("utf-8")
        print(f"Render sync response: {result_body}")

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": f"Successfully synced {len(data)} statements to Render",
            "count": len(data)
        })
    }

# Local test execution
if __name__ == "__main__":
    res = lambda_handler(None, None)
    print("Test result:", res)

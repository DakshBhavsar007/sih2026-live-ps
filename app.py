import os
import json
import logging
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from sih_scraper import get_live_submissions, set_cached_submissions, CACHE_TTL_SECONDS, SIH_SOURCE_URL

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sih_server")

app = Flask(__name__, static_folder=".")

# Configure CORS
cors_origin = os.environ.get("CORS_ORIGIN", "*")
CORS(app, resources={r"/api/*": {"origins": cors_origin}})

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATEMENTS_JSON_PATH = os.path.join(BASE_DIR, "sih2026_problem_statements.json")
SYNC_SECRET = os.environ.get("SYNC_SECRET", "")

@app.route("/api/sih/submissions", methods=["GET"])
def submissions_endpoint():
    """
    Preferred live submission counts endpoint:
    GET /api/sih/submissions
    Query params:
      - force (bool, e.g. ?force=true): bypass cache and fetch directly from SIH
    Always returns HTTP 200 with data (fresh or stale cache fallback).
    """
    force = request.args.get("force", "").lower() in ("true", "1", "yes")
    result = get_live_submissions(force_refresh=force)
    return jsonify(result), 200

@app.route("/api/sih/sync", methods=["POST"])
def sync_endpoint():
    """
    Push Sync Endpoint:
    Allows pushing newly scraped submission counts directly into memory cache.
    Bypasses NIC firewall cloud IP blocking by receiving updates scraped from Indian clients/workers.
    """
    if SYNC_SECRET:
        token = request.headers.get("X-Sync-Token") or request.args.get("token")
        if token != SYNC_SECRET:
            return jsonify({"error": "Unauthorized"}), 401

    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "Invalid or missing JSON payload"}), 400

    data_dict = payload.get("data") if isinstance(payload, dict) and "data" in payload else payload
    if not isinstance(data_dict, dict) or len(data_dict) == 0:
        return jsonify({"error": "Payload must contain a non-empty dictionary"}), 400

    success = set_cached_submissions(data_dict)
    if success:
        return jsonify({
            "success": True,
            "message": f"Successfully updated cache with {len(data_dict)} problem statements",
            "count": len(data_dict)
        }), 200
    return jsonify({"error": "Failed to update cache"}), 500

@app.route("/api/sih/statements", methods=["GET"])
def statements_endpoint():
    """
    Returns the static 240 Problem Statements dataset directly from local storage.
    """
    if os.path.exists(STATEMENTS_JSON_PATH):
        try:
            with open(STATEMENTS_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return jsonify(data), 200
        except Exception as e:
            return jsonify({"error": f"Failed to read statements: {e}"}), 500
    return jsonify({"error": "Dataset file not found"}), 404

@app.route("/api/health", methods=["GET"])
@app.route("/health", methods=["GET"])
def health_endpoint():
    return jsonify({
        "status": "healthy",
        "service": "SIH 2026 Live Submission Backend",
        "sih_source": SIH_SOURCE_URL,
        "cache_ttl_seconds": CACHE_TTL_SECONDS
    }), 200

@app.route("/favicon.ico", methods=["GET"])
def favicon():
    """Prevent 404 error in browser console for favicon."""
    return "", 204

@app.route("/", methods=["GET"])
def root_index():
    for filename in ["SIH2026-Problem-Statements.html", "index.html"]:
        if os.path.exists(os.path.join(BASE_DIR, filename)):
            return send_from_directory(BASE_DIR, filename)
    return "SIH 2026 PS Dashboard UI file not found", 404

@app.route("/<path:path>", methods=["GET"])
def serve_static(path):
    if os.path.exists(os.path.join(BASE_DIR, path)):
        return send_from_directory(BASE_DIR, path)
    return jsonify({"error": "Not found"}), 404

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0")
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    logger.info(f"Starting SIH 2026 Live Submission Backend on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)

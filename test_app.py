import unittest
import json
from app import app
import sih_scraper

class TestSIHBackendApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()
        # Warmup
        cls.client.get("/api/sih/submissions")

    def test_1_health_endpoint(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "healthy")

    def test_2_submissions_endpoint_schema_and_counts(self):
        resp = self.client.get("/api/sih/submissions")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        
        self.assertTrue(data["success"])
        self.assertEqual(data["source"], "https://www.sih.gov.in/sih2026PS")
        self.assertIn("updated_at", data)
        self.assertIn("data", data)
        
        records = data["data"]
        self.assertEqual(len(records), 240, f"Expected 240 records, found {len(records)}")
        
        # Verify specific problem statements
        self.assertIn("SIH26001", records)
        ps1 = records["SIH26001"]
        self.assertEqual(ps1["submitted"], 500)
        self.assertEqual(ps1["capacity"], 500)
        self.assertEqual(ps1["display"], "500/500")

        self.assertIn("SIH26163", records)
        ps163 = records["SIH26163"]
        self.assertEqual(ps163["submitted"], 23)
        self.assertEqual(ps163["capacity"], 500)
        self.assertEqual(ps163["display"], "23/500")

        # Verify all records have numeric submitted and capacity
        for ps_id, val in records.items():
            self.assertIsInstance(val["submitted"], int, f"{ps_id} submitted is not int: {val}")
            self.assertIsInstance(val["capacity"], int, f"{ps_id} capacity is not int: {val}")
            self.assertTrue("/" in val["display"], f"{ps_id} display is invalid: {val}")

    def test_3_numeric_sorting_logic(self):
        resp = self.client.get("/api/sih/submissions")
        records = resp.get_json()["data"]

        # Simulate sorting High -> Low as implemented in frontend
        sorted_desc = sorted(
            records.items(),
            key=lambda item: (item[1]["submitted"], item[0]),
            reverse=True
        )
        
        counts_desc = [item[1]["submitted"] for item in sorted_desc]
        self.assertEqual(counts_desc, sorted(counts_desc, reverse=True))
        self.assertGreaterEqual(counts_desc[0], counts_desc[-1])
        print(f"Top 5 submissions (High->Low): {[f'{k}: {v['display']}' for k, v in sorted_desc[:5]]}")
        print(f"Bottom 5 submissions (High->Low): {[f'{k}: {v['display']}' for k, v in sorted_desc[-5:]]}")

        # Verify numeric property: e.g. 500 comes before 90, 23, 7
        sorted_asc = sorted(
            records.items(),
            key=lambda item: (item[1]["submitted"], item[0])
        )
        counts_asc = [item[1]["submitted"] for item in sorted_asc]
        self.assertEqual(counts_asc, sorted(counts_asc))

    def test_4_cache_hit_and_force_refresh(self):
        # Normal call should be cached
        resp = self.client.get("/api/sih/submissions")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["cached"])

        # Force refresh parameter
        resp_forced = self.client.get("/api/sih/submissions?force=true")
        self.assertEqual(resp_forced.status_code, 200)
        self.assertFalse(resp_forced.get_json()["cached"])

    def test_5_stale_fallback_when_sih_down(self):
        orig_fetch = sih_scraper.fetch_sih_html
        try:
            def fail_fetch(*args, **kwargs):
                raise ConnectionError("Temporary SIH portal outage")
            sih_scraper.fetch_sih_html = fail_fetch

            # Forced request fails, but returns cached data marked stale
            resp = self.client.get("/api/sih/submissions?force=true")
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data["success"])
            self.assertTrue(data["cached"])
            self.assertTrue(data["stale"])
            self.assertIn("warning", data)
            self.assertEqual(len(data["data"]), 240)
        finally:
            sih_scraper.fetch_sih_html = orig_fetch

    def test_6_static_statements_endpoint(self):
        resp = self.client.get("/api/sih/statements")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        items = data.get("problem_statements", [])
        self.assertEqual(len(items), 240)

    def test_7_root_dashboard_serving(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"SIH 2026 Problem Statements", resp.data)
        self.assertIn(b"Sync Now", resp.data)
        self.assertIn(b"/api/sih/submissions", resp.data)

if __name__ == "__main__":
    unittest.main()

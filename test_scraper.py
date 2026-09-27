import unittest
import time
from sih_scraper import get_live_submissions, _cache

class TestSIHScraper(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        print("\n--- Initial Warmup / Fetch ---")
        get_live_submissions(force_refresh=True)

    def test_1_live_fetch(self):
        print("\n--- Testing Live SIH Force Refresh ---")
        t0 = time.time()
        res = get_live_submissions(force_refresh=True)
        print(f"Fetch completed in {time.time() - t0:.2f}s")
        
        self.assertTrue(res["success"])
        self.assertEqual(res["source"], "https://www.sih.gov.in/sih2026PS")
        self.assertFalse(res["cached"])
        self.assertFalse(res["stale"])
        self.assertIsNotNone(res["updated_at"])
        
        data = res["data"]
        self.assertEqual(len(data), 240, f"Expected 240 records, got {len(data)}")
        print(f"Total PS parsed: {len(data)}")
        
        # Verify SIH26001
        self.assertIn("SIH26001", data)
        ps1 = data["SIH26001"]
        print("SIH26001:", ps1)
        self.assertEqual(ps1["submitted"], 500)
        self.assertEqual(ps1["capacity"], 500)
        self.assertEqual(ps1["display"], "500/500")
        
        # Verify SIH26163
        self.assertIn("SIH26163", data)
        ps163 = data["SIH26163"]
        print("SIH26163:", ps163)
        self.assertEqual(ps163["submitted"], 23)
        self.assertEqual(ps163["capacity"], 500)
        self.assertEqual(ps163["display"], "23/500")

    def test_2_cache_hit(self):
        print("\n--- Testing Cache Hit ---")
        t0 = time.time()
        res = get_live_submissions(force_refresh=False)
        duration = time.time() - t0
        print(f"Cache hit returned in {duration:.4f}s")
        self.assertTrue(res["cached"])
        self.assertFalse(res["stale"])
        self.assertLess(duration, 0.05)
        self.assertEqual(len(res["data"]), 240)

    def test_3_stale_fallback(self):
        print("\n--- Testing Stale Fallback on Error ---")
        import sih_scraper
        orig_fetch = sih_scraper.fetch_sih_html
        try:
            def fail_fetch(*args, **kwargs):
                raise ConnectionError("Simulated SIH portal downtime")
            sih_scraper.fetch_sih_html = fail_fetch
            
            # Force refresh should fail and gracefully return stale cache
            res = sih_scraper.get_live_submissions(force_refresh=True)
            self.assertTrue(res["success"])
            self.assertTrue(res["cached"])
            self.assertTrue(res["stale"])
            self.assertIn("warning", res)
            self.assertIn("SIH26001", res["data"])
            print("Successfully recovered cached data marked as stale!")
        finally:
            sih_scraper.fetch_sih_html = orig_fetch

if __name__ == "__main__":
    unittest.main()

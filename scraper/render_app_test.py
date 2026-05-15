import json
import os
import unittest
from unittest.mock import patch

import app


def fake_results():
    base = [
        {"id": str(index), "name": f"Loteria {index}", "date": "02-05-2026", "number": "01-02-03"}
        for index in range(1, 19)
    ] + [
        {"id": "19", "name": "NJ Pick 3 Día", "date": "02-05-2026", "number": "3-7-1"},
        {"id": "20", "name": "NJ Pick 3 Noche", "date": "02-05-2026", "number": "5-3-4"},
        {"id": "21", "name": "NJ Pick 4 Día", "date": "02-05-2026", "number": "0-8-4-3"},
        {"id": "22", "name": "NJ Pick 4 Noche", "date": "02-05-2026", "number": "1-2-2-4"},
        {"id": "23", "name": "King Lottery Día", "date": "02-05-2026", "number": "90-76-95"},
        {"id": "24", "name": "King Lottery Noche", "date": "02-05-2026", "number": "85-31-78"},
        {"id": "25", "name": "New Jersey AM", "date": "02-05-2026", "number": "71-08-43"},
        {"id": "26", "name": "New Jersey PM", "date": "02-05-2026", "number": "34-12-24"},
        {"id": "27", "name": "Haiti Bolet 11:30 AM", "date": "02-05-2026", "number": "03-21-01"},
        {"id": "28", "name": "Haiti Bolet 6:30 PM", "date": "02-05-2026", "number": "52-35-42"},
    ]
    return base


class RenderAppContractsTest(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()
        app._scrape_cache.clear()
        app._pick_scrape_cache.clear()
        app._lottery_refresh_inflight.clear()
        app._pick_refresh_inflight.clear()
        app._pick_refresh_last_started.clear()
        app._live_system_results_cache.clear()
        app._manual_override_cache.clear()
        app._supabase_cache.clear()
        app.INTERNAL_SHARED_SECRET = ""

    def test_unique_sorted_results_deduplicates(self):
        rows = [
            {"id": "2", "name": "Anguila Mañana", "date": "02-05", "number": "68-64-42"},
            {"id": "2", "name": "Anguila Mañana", "date": "02-05", "number": "68-64-42"},
            {"id": "28", "name": "Haiti Bolet 6:30 PM", "date": "02-05-2026", "number": "52-35-42"},
            {"id": "27", "name": "Haiti Bolet 11:30 AM", "date": "02-05-2026", "number": "03-21-01"},
        ]

        unique = app.unique_sorted_results(rows)

        self.assertEqual(["2", "27", "28"], [row["id"] for row in unique])

    def test_wsgi_root_keeps_legacy_list_shape(self):
        rows = [{"id": "27", "name": "Haiti Bolet 11:30 AM", "date": "02-05-2026", "number": "03-21-01"}]

        with patch("app.fetch_existing_from_supabase", return_value=rows), \
                patch("app.fetch_pick_rows_from_supabase", return_value=[]), \
                patch("app.scrape") as scrape, \
                patch("app.scrape_us_picks") as scrape_picks:
            response = self.client.get("/?date=02-05-2026")

        scrape.assert_not_called()
        scrape_picks.assert_not_called()
        payload = json.loads(response.data.decode("utf-8"))
        self.assertEqual(200, response.status_code)
        self.assertEqual("27", payload[0]["id"])

    def test_wsgi_root_without_date_is_lightweight_health_check(self):
        with patch("app.scrape") as scrape, patch("app.scrape_us_picks") as scrape_picks:
            response = self.client.get("/")

        scrape.assert_not_called()
        scrape_picks.assert_not_called()
        payload = json.loads(response.data.decode("utf-8"))
        self.assertEqual(200, response.status_code)
        self.assertTrue(payload["ok"])
        self.assertEqual("lotterynet-results", payload["service"])

    def test_wsgi_system_results_returns_lotteries_and_picks_sections(self):
        rows = [{"id": "1", "name": "La Primera Día", "date": "02-05-2026", "number": "01-02-03"}]
        pick_rows = [{
            "id": "US-P3-MN-PICK-3-DAY",
            "state": "Minnesota",
            "game": "pick3",
            "gameName": "Pick 3",
            "draw": "Day Draw",
            "date": "02-05-2026",
            "number": "5-6-1",
        }]

        with patch("app.fetch_existing_from_supabase", return_value=rows), \
                patch("app.fetch_pick_rows_from_supabase", return_value=pick_rows), \
                patch("app.scrape") as scrape, \
                patch("app.scrape_us_picks") as scrape_picks:
            response = self.client.get("/system-results?date=02-05-2026&mode=both")

        scrape.assert_not_called()
        scrape_picks.assert_not_called()
        payload = json.loads(response.data.decode("utf-8"))
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, payload["lotteries"]["count"])
        self.assertEqual(1, payload["picks"]["count"])
        self.assertEqual("5-6-1", payload["picks"]["results"][0]["pick3"])

    def test_system_results_uses_supabase_cache_without_scraping(self):
        cached_lotteries = [{"id": "1", "name": "La Primera Día", "date": "11-05-2026", "number": "19-93-58"}]
        cached_picks = [{
            "id": "US-P3-FL-PICK-3-MIDDAY",
            "state": "Florida",
            "game": "pick3",
            "gameName": "Pick 3",
            "draw": "Midday Draw",
            "date": "11-05-2026",
            "number": "1-2-3",
        }]

        with patch("app.fetch_existing_from_supabase", return_value=cached_lotteries), \
                patch("app.fetch_pick_rows_from_supabase", return_value=cached_picks), \
                patch("app.scrape") as scrape, \
                patch("app.scrape_us_picks") as scrape_picks:
            response = self.client.get("/system-results?date=11-05-2026&mode=both")

        scrape.assert_not_called()
        scrape_picks.assert_not_called()
        payload = json.loads(response.data.decode("utf-8"))
        self.assertEqual("supabase-cache", payload["source"])
        self.assertEqual(1, payload["lotteries"]["count"])
        self.assertEqual(1, payload["picks"]["count"])

    def test_system_results_splits_legacy_mixed_cache_when_pick_cache_missing(self):
        mixed_cache = [
            {"id": "1", "name": "La Primera Día", "date": "11-05-2026", "number": "19-93-58"},
            {
                "id": "US-P3-FL-PICK-3-MIDDAY",
                "name": "Florida Pick 3 Midday Draw",
                "date": "11-05-2026",
                "number": "1-2-3",
                "pick3": "1-2-3",
            },
        ]

        with patch("app.fetch_existing_from_supabase", return_value=mixed_cache), \
                patch("app.fetch_pick_rows_from_supabase", return_value=[]), \
                patch("app.scrape") as scrape, \
                patch("app.scrape_us_picks") as scrape_picks:
            response = self.client.get("/system-results?date=11-05-2026&mode=both")

        scrape.assert_not_called()
        scrape_picks.assert_not_called()
        payload = json.loads(response.data.decode("utf-8"))
        self.assertEqual(["1"], [row["id"] for row in payload["lotteries"]["results"]])
        self.assertEqual(["US-P3-FL-PICK-3-MIDDAY"], [row["id"] for row in payload["picks"]["results"]])

    def test_public_results_do_not_scrape_when_cache_is_missing(self):
        with patch("app.fetch_existing_from_supabase", return_value=[]), \
                patch("app.fetch_pick_rows_from_supabase", return_value=[]), \
                patch("app.scrape") as scrape, \
                patch("app.scrape_us_picks") as scrape_picks:
            response = self.client.get("/results?date=11-05-2026")

        scrape.assert_not_called()
        scrape_picks.assert_not_called()
        payload = json.loads(response.data.decode("utf-8"))
        self.assertEqual("cache-miss", payload["source"])
        self.assertEqual(0, payload["count"])

    def test_run_results_response_includes_28_lotteries_when_scraper_has_all(self):
        rows = [
            {"id": str(index), "name": f"Loteria {index}", "date": "02-05-2026", "number": "01-02-03"}
            for index in range(1, 29)
        ]

        with patch("app.scrape", return_value=rows), \
                patch("app.scrape_us_picks", return_value=[]), \
                patch("app.save_to_supabase") as save_lottery, \
                patch("app.save_us_picks_to_supabase") as save_pick, \
                patch("app.SUPABASE_KEY", "test-key"):
            response = self.client.get("/run-scraper?date=02-05-2026")

        payload = json.loads(response.data.decode("utf-8"))
        self.assertEqual(200, response.status_code)
        self.assertEqual(28, payload["count"])
        self.assertTrue(payload["saved"])
        save_lottery.assert_called_once()
        save_pick.assert_called_once()

    def test_run_results_response_includes_pick_three_and_pick_four_rows(self):
        rows = [{"id": "1", "name": "Loteria 1", "date": "02-05-2026", "number": "01-02-03"}]
        pick_rows = [
            {
                "id": "US-P3-AZ-PICK-3-1-00-PM",
                "name": "Arizona Pick 3",
                "state": "Arizona",
                "game": "pick3",
                "gameName": "Pick 3",
                "draw": "1:00 PM",
                "date": "02-05-2026",
                "number": "2-6-4",
            },
            {
                "id": "US-P4-FL-PICK-4-9-45-PM",
                "name": "Florida Pick 4",
                "state": "Florida",
                "game": "pick4",
                "gameName": "Pick 4",
                "draw": "9:45 PM",
                "date": "02-05-2026",
                "number": "2-5-4-6",
            },
        ]

        with patch("app.scrape", return_value=rows), \
                patch("app.scrape_us_picks", return_value=pick_rows), \
                patch("app.save_to_supabase") as save_lottery, \
                patch("app.save_us_picks_to_supabase") as save_pick, \
                patch("app.SUPABASE_KEY", "test-key"):
            response = self.client.get("/run-scraper?date=02-05-2026")

        payload = json.loads(response.data.decode("utf-8"))
        self.assertEqual(200, response.status_code)
        self.assertEqual(3, payload["count"])
        self.assertTrue(payload["saved"])
        self.assertEqual("2-6-4", payload["results"][1]["pick3"])
        self.assertEqual("2-5-4-6", payload["results"][2]["pick4"])
        save_lottery.assert_called_once()
        save_pick.assert_called_once()

    def test_run_results_response_warms_in_memory_cache_after_save(self):
        lottery_rows = [{"id": "1", "name": "La Primera Día", "date": "11-05-2026", "number": "19-93-58"}]
        pick_rows = [{
            "id": "US-P3-FL-PICK-3-MIDDAY",
            "state": "Florida",
            "game": "pick3",
            "gameName": "Pick 3",
            "draw": "Midday Draw",
            "date": "11-05-2026",
            "number": "1-2-3",
        }]

        app._supabase_cache.clear()
        with patch("app.scrape", return_value=lottery_rows), \
                patch("app.scrape_us_picks", return_value=pick_rows), \
                patch("app.save_to_supabase"), \
                patch("app.save_us_picks_to_supabase"), \
                patch("app.SUPABASE_KEY", "test-key"):
            self.client.get("/run-scraper?date=11-05-2026")

        cached_lottery = app.fetch_supabase_results_cache_cached("lot_results_cache_by_day:11-05-2026")
        self.assertEqual(lottery_rows, cached_lottery)
        cached_pick = app.fetch_supabase_results_cache_cached("pick_results_cache_by_day:11-05-2026")
        self.assertEqual(["US-P3-FL-PICK-3-MIDDAY"], [row["id"] for row in cached_pick])

    def test_run_pick_results_response_warms_pick_cache_after_save(self):
        pick_rows = [{
            "id": "US-P3-FL-PICK-3-MIDDAY",
            "state": "Florida",
            "game": "pick3",
            "gameName": "Pick 3",
            "draw": "Midday Draw",
            "date": "11-05-2026",
            "number": "1-2-3",
        }]

        app._supabase_cache.clear()
        with patch("app.scrape_us_picks", return_value=pick_rows), \
                patch("app.save_us_picks_to_supabase") as save_pick, \
                patch("app.SUPABASE_KEY", "test-key"):
            response = self.client.get("/run-pick-scraper?date=11-05-2026")

        save_pick.assert_called_once()
        payload = json.loads(response.data.decode("utf-8"))
        self.assertTrue(payload["saved"])
        cached_pick = app.fetch_supabase_results_cache_cached("pick_results_cache_by_day:11-05-2026")
        self.assertEqual(["US-P3-FL-PICK-3-MIDDAY"], [row["id"] for row in cached_pick])

    def test_internal_supabase_cache_invalidate_clears_results_sections_for_date(self):
        app.INTERNAL_SHARED_SECRET = "secret"
        app._supabase_cache["lot_results_cache_by_day:11-05-2026"] = {"stored_at": 1, "data": [{"id": "1"}]}
        app._supabase_cache["pick_results_cache_by_day:11-05-2026"] = {"stored_at": 1, "data": [{"id": "19"}]}
        app._manual_override_cache["11-05-2026"] = {"stored_at": 1, "rows": [{"id": "1"}]}
        app._live_system_results_cache["11-05-2026:both"] = {"stored_at": 1, "payload": {"date": "11-05-2026"}}

        response = self.client.post(
            "/internal/supabase-cache-invalidate",
            headers={"x-lotterynet-admin-secret": "secret"},
            json={"record": {"key": "lot_results_cache_by_day:11-05-2026"}},
        )

        payload = json.loads(response.data.decode("utf-8"))
        self.assertEqual(200, response.status_code)
        self.assertTrue(payload["ok"])
        self.assertEqual(["lot_results_cache_by_day:11-05-2026"], payload["invalidatedKeys"])
        self.assertNotIn("lot_results_cache_by_day:11-05-2026", app._supabase_cache)
        self.assertNotIn("11-05-2026", app._manual_override_cache)
        self.assertNotIn("11-05-2026:both", app._live_system_results_cache)

    def test_internal_cache_invalidate_allows_public_results_keys_without_secret(self):
        app._supabase_cache["lot_results_cache_by_day:11-05-2026"] = {"stored_at": 1, "data": [{"id": "1"}]}

        response = self.client.post(
            "/internal/supabase-cache-invalidate",
            json={"key": "lot_results_cache_by_day:11-05-2026"},
        )

        payload = json.loads(response.data.decode("utf-8"))
        self.assertEqual(200, response.status_code)
        self.assertTrue(payload["ok"])
        self.assertEqual(["lot_results_cache_by_day:11-05-2026"], payload["invalidatedKeys"])
        self.assertNotIn("lot_results_cache_by_day:11-05-2026", app._supabase_cache)

    def test_internal_cache_invalidate_rejects_non_results_keys_without_secret(self):
        response = self.client.post(
            "/internal/supabase-cache-invalidate",
            json={"key": "cashier_limits:owner-a"},
        )

        payload = json.loads(response.data.decode("utf-8"))
        self.assertEqual(403, response.status_code)
        self.assertFalse(payload["ok"])

    def test_internal_cache_invalidate_clears_snapshot_and_live_sections(self):
        app._supabase_cache["lot_results_cache_by_day:11-05-2026"] = ([{"id": "1"}], 1.0)
        app._manual_override_cache["11-05-2026"] = ([{"id": "19"}], 1.0)
        app._live_system_results_cache[("11-05-2026", "both")] = ({"servedFrom": "response-cache"}, 1.0)
        app._live_system_results_cache[("11-05-2026", "pick")] = ({"servedFrom": "response-cache"}, 1.0)

        with patch.dict(os.environ, {"LOTTERYNET_ADMIN_SHARED_SECRET": "secret"}, clear=False):
            app.INTERNAL_SHARED_SECRET = "secret"
            response = self.client.post(
                "/internal/supabase-cache-invalidate",
                headers={"x-lotterynet-admin-secret": "secret"},
                json={"record": {"key": "manual_results_overrides_by_day:11-05-2026"}},
            )

        payload = json.loads(response.data.decode("utf-8"))
        self.assertEqual(200, response.status_code)
        self.assertTrue(payload["ok"])
        self.assertEqual(["manual_results_overrides_by_day:11-05-2026"], payload["invalidatedKeys"])
        self.assertNotIn("11-05-2026", app._manual_override_cache)
        self.assertNotIn(("11-05-2026", "both"), app._live_system_results_cache)
        self.assertNotIn(("11-05-2026", "pick"), app._live_system_results_cache)

    def test_api_v1_health_returns_version(self):
        response = self.client.get("/api/v1/health")
        payload = json.loads(response.data.decode("utf-8"))
        self.assertEqual(200, response.status_code)
        self.assertTrue(payload["ok"])
        self.assertEqual("v1", payload["version"])

    def test_api_v1_scrape_routes_scraper(self):
        rows = [{"id": "1", "name": "Loteria 1", "date": "02-05-2026", "number": "01-02-03"}]
        with patch("app.scrape", return_value=rows), \
                patch("app.scrape_us_picks", return_value=[]), \
                patch("app.save_to_supabase"), \
                patch("app.save_us_picks_to_supabase"), \
                patch("app.SUPABASE_KEY", "test-key"):
            response = self.client.post("/api/v1/scrape?date=02-05-2026")

        payload = json.loads(response.data.decode("utf-8"))
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, payload["count"])
        self.assertTrue(payload["saved"])

    def test_wsgi_application_backward_compat(self):
        rows = [{"id": "27", "name": "Haiti Bolet 11:30 AM", "date": "02-05-2026", "number": "03-21-01"}]
        status_headers = {}

        def start_response(status, headers):
            status_headers["status"] = status
            status_headers["headers"] = dict(headers)

        with patch("app.fetch_existing_from_supabase", return_value=rows), \
                patch("app.fetch_pick_rows_from_supabase", return_value=[]), \
                patch("app.scrape") as scrape, \
                patch("app.scrape_us_picks") as scrape_picks:
            body = b"".join(app.application(
                {"PATH_INFO": "/", "QUERY_STRING": "date=02-05-2026",
                 "REQUEST_METHOD": "GET", "SERVER_NAME": "test", "SERVER_PORT": "80",
                 "wsgi.url_scheme": "http"},
                start_response,
            ))

        scrape.assert_not_called()
        scrape_picks.assert_not_called()
        self.assertEqual("200 OK", status_headers["status"])
        self.assertEqual("27", json.loads(body.decode("utf-8"))[0]["id"])


if __name__ == "__main__":
    unittest.main()

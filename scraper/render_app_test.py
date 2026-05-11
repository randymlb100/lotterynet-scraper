import json
import unittest
from unittest.mock import patch

import app


class RenderAppContractsTest(unittest.TestCase):
    def test_root_returns_unique_sorted_results(self):
        rows = [
            {"id": "2", "name": "Anguila Mañana", "date": "02-05", "number": "68-64-42"},
            {"id": "2", "name": "Anguila Mañana", "date": "02-05", "number": "68-64-42"},
            {"id": "28", "name": "Haiti Bolet 6:30 PM", "date": "02-05-2026", "number": "52-35-42"},
            {"id": "27", "name": "Haiti Bolet 11:30 AM", "date": "02-05-2026", "number": "03-21-01"},
        ]

        unique = app.unique_sorted_results(rows)

        self.assertEqual(["2", "27", "28"], [row["id"] for row in unique])

    def test_run_results_response_includes_28_lotteries_when_scraper_has_all(self):
        rows = [
            {"id": str(index), "name": f"Loteria {index}", "date": "02-05-2026", "number": "01-02-03"}
            for index in range(1, 29)
        ]

        with patch("app.scrape", return_value=rows), patch("app.scrape_us_picks", return_value=[]):
            response = app.build_results_response(date_key="02-05-2026", save=True)

        self.assertEqual("02-05-2026", response["date"])
        self.assertEqual(28, response["count"])
        self.assertEqual("28", response["results"][-1]["id"])

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

        with patch("app.scrape", return_value=rows), patch("app.scrape_us_picks", return_value=pick_rows):
            response = app.build_results_response(date_key="02-05-2026", save=True)

        self.assertEqual(3, response["count"])
        self.assertEqual(2, response["pickCount"])
        self.assertEqual("2-6-4", response["results"][1]["pick3"])
        self.assertEqual("2-5-4-6", response["results"][2]["pick4"])
        self.assertEqual("Arizona Pick 3 1:00 PM", response["results"][1]["name"])

    def test_wsgi_root_keeps_legacy_list_shape(self):
        rows = [{"id": "27", "name": "Haiti Bolet 11:30 AM", "date": "02-05-2026", "number": "03-21-01"}]

        status_headers = {}

        def start_response(status, headers):
            status_headers["status"] = status
            status_headers["headers"] = dict(headers)

        with patch("app.fetch_supabase_results_cache", side_effect=[rows, []]), \
                patch("app.scrape") as scrape, \
                patch("app.scrape_us_picks") as scrape_picks:
            body = b"".join(app.application({"PATH_INFO": "/", "QUERY_STRING": "date=02-05-2026"}, start_response))

        scrape.assert_not_called()
        scrape_picks.assert_not_called()
        self.assertEqual("200 OK", status_headers["status"])
        self.assertEqual("application/json; charset=utf-8", status_headers["headers"]["Content-Type"])
        self.assertEqual("27", json.loads(body.decode("utf-8"))[0]["id"])

    def test_wsgi_root_without_date_is_lightweight_health_check(self):
        status_headers = {}

        def start_response(status, headers):
            status_headers["status"] = status
            status_headers["headers"] = dict(headers)

        with patch("app.scrape") as scrape, patch("app.scrape_us_picks") as scrape_picks:
            body = b"".join(app.application({"PATH_INFO": "/", "QUERY_STRING": ""}, start_response))

        scrape.assert_not_called()
        scrape_picks.assert_not_called()
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual("200 OK", status_headers["status"])
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
        status_headers = {}

        def start_response(status, headers):
            status_headers["status"] = status
            status_headers["headers"] = dict(headers)

        with patch("app.fetch_supabase_results_cache", side_effect=[rows, pick_rows]), \
                patch("app.scrape") as scrape, \
                patch("app.scrape_us_picks") as scrape_picks:
            body = b"".join(app.application(
                {"PATH_INFO": "/system-results", "QUERY_STRING": "date=02-05-2026&mode=both"},
                start_response,
            ))

        scrape.assert_not_called()
        scrape_picks.assert_not_called()
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual("200 OK", status_headers["status"])
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

        with patch("app.fetch_supabase_results_cache", side_effect=[cached_lotteries, cached_picks]), \
                patch("app.scrape") as scrape, \
                patch("app.scrape_us_picks") as scrape_picks:
            payload = app.build_system_results_response(date_key="11-05-2026", mode="both")

        scrape.assert_not_called()
        scrape_picks.assert_not_called()
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

        with patch("app.fetch_supabase_results_cache", side_effect=[mixed_cache, []]), \
                patch("app.scrape") as scrape, \
                patch("app.scrape_us_picks") as scrape_picks:
            payload = app.build_system_results_response(date_key="11-05-2026", mode="both")

        scrape.assert_not_called()
        scrape_picks.assert_not_called()
        self.assertEqual(["1"], [row["id"] for row in payload["lotteries"]["results"]])
        self.assertEqual(["US-P3-FL-PICK-3-MIDDAY"], [row["id"] for row in payload["picks"]["results"]])

    def test_public_results_do_not_scrape_when_cache_is_missing(self):
        with patch("app.fetch_supabase_results_cache", return_value=[]), \
                patch("app.scrape") as scrape, \
                patch("app.scrape_us_picks") as scrape_picks:
            response = app.build_results_response(date_key="11-05-2026")

        scrape.assert_not_called()
        scrape_picks.assert_not_called()
        self.assertEqual("cache-miss", response["source"])
        self.assertEqual(0, response["count"])

    def test_public_system_results_do_not_scrape_when_cache_is_missing(self):
        with patch("app.fetch_supabase_results_cache", return_value=[]), \
                patch("app.scrape") as scrape, \
                patch("app.scrape_us_picks") as scrape_picks:
            payload = app.build_system_results_response(date_key="11-05-2026", mode="both")

        scrape.assert_not_called()
        scrape_picks.assert_not_called()
        self.assertEqual("cache-miss", payload["source"])
        self.assertEqual(0, payload["lotteries"]["count"])
        self.assertEqual(0, payload["picks"]["count"])


if __name__ == "__main__":
    unittest.main()

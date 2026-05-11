import unittest
from unittest.mock import patch

import app


class AppContractsTest(unittest.TestCase):
    def test_combined_results_include_pick_rows_with_non_numeric_ids(self):
        with patch("app.fetch_supabase_results_cache", side_effect=[[], [
            {
                "id": "US-P3-FL-PICK-3-MIDDAY",
                "state": "Florida",
                "stateCode": "FL",
                "game": "pick3",
                "gameName": "Pick 3",
                "draw": "Midday Draw",
                "date": "08-05-2026",
                "number": "1-2-3",
                "source": "pick-3.com",
            },
            {
                "id": "US-P3-FL-PICK-3-EVENING",
                "state": "Florida",
                "stateCode": "FL",
                "game": "pick3",
                "gameName": "Pick 3",
                "draw": "Evening Draw",
                "date": "08-05-2026",
                "number": "9-2-0",
                "source": "pick-3.com",
            },
        ]]), patch("app.scrape") as scrape, patch("app.scrape_us_picks") as scrape_picks:
            payload = app.build_results_response(date_key="08-05-2026")

        scrape.assert_not_called()
        scrape_picks.assert_not_called()
        self.assertEqual(2, payload["pickCount"])
        self.assertEqual(
            ["US-P3-FL-PICK-3-EVENING", "US-P3-FL-PICK-3-MIDDAY"],
            [row["id"] for row in payload["results"]],
        )
        self.assertEqual(
            ["Florida Pick 3 Evening Draw", "Florida Pick 3 Midday Draw"],
            [row["name"] for row in payload["results"]],
        )
        self.assertEqual(["9-2-0", "1-2-3"], [row["pick3"] for row in payload["results"]])


if __name__ == "__main__":
    unittest.main()

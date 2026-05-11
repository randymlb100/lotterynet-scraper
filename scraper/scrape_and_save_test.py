import os
import unittest
import datetime

import scrape_and_save as scraper


class ScraperContractsTest(unittest.TestCase):
    def test_authoritative_nj_ids_cover_pick_and_new_jersey(self):
        self.assertEqual({"19", "20", "21", "22", "25", "26"}, scraper.AUTHORITATIVE_NJ_IDS)

    def test_tracked_remote_ids_include_king_and_haiti_bolet(self):
        self.assertEqual({"23", "24", "27", "28"}, scraper.TRACKED_REMOTE_RESULT_IDS)

    def test_miloteria_maps_new_jersey_pm(self):
        self.assertEqual("26", scraper.MILOTERIA_NJ_MAP["new jersey pm"]["id"])
        self.assertEqual("New Jersey PM", scraper.MILOTERIA_NJ_MAP["new jersey pm"]["name"])

    def test_us_pick_result_ids_include_draw_label(self):
        self.assertEqual(
            "US-P3-FL-PICK-3-MIDDAY",
            scraper.build_us_pick_result_id("pick3", "FL", "Pick 3", "Midday Draw"),
        )
        self.assertEqual(
            "US-P4-NY-WIN-4-EVENING",
            scraper.build_us_pick_result_id("pick4", "NY", "Win 4", "Evening Draw"),
        )

    def test_parse_pick_overview_keeps_midday_and_evening_as_separate_rows(self):
        html = """
        <section>
          <img alt="Florida Pick 3 Latest Draws!" />
          <p>08 May 26 Midday Draw</p>
          <ul><li>1</li><li>2</li><li>3</li></ul>
          <a href="https://fl.pick-3.com">Check Numbers</a>
        </section>
        <section>
          <img alt="Florida Pick 3 Latest Draws!" />
          <p>08 May 26 Evening Draw</p>
          <ul><li>9</li><li>2</li><li>0</li></ul>
          <a href="https://fl.pick-3.com">Check Numbers</a>
        </section>
        """

        rows = scraper.parse_us_pick_overview(html, game="pick3")

        self.assertEqual(
            ["US-P3-FL-PICK-3-EVENING", "US-P3-FL-PICK-3-MIDDAY"],
            sorted(row["id"] for row in rows),
        )
        self.assertEqual(["1-2-3", "9-2-0"], sorted(row["number"] for row in rows))

    def test_parse_pick_overview_keeps_new_jersey_pick_rows(self):
        html = """
        <section>
          <img alt="New Jersey Pick 3 Latest Draws!" />
          <p>08 May 26 Midday Draw</p>
          <ul><li>3</li><li>8</li><li>3</li></ul>
          <a href="https://nj.pick-3.com">Check Numbers</a>
        </section>
        """

        rows = scraper.parse_us_pick_overview(html, game="pick3")

        self.assertEqual(["US-P3-NJ-PICK-3-MIDDAY"], [row["id"] for row in rows])
        self.assertEqual(["3-8-3"], [row["number"] for row in rows])

    def test_parse_new_jersey_pick_home_keeps_midday_and_evening_without_fireball(self):
        html = """
        <div class="resultsHome">
          <div class="date">Saturday, May 9, 2026</div>
          <div class="result-box">
            <div class="box">
              <div class="text">Midday</div>
              <ul class="balls">
                <li class="resultBall ball number-part-01">4</li>
                <li class="resultBall ball number-part-02">7</li>
                <li class="resultBall ball number-part-03">6</li>
                <li class="resultBall ball number-part-04">1</li>
                <li class="resultBall ball fireball">6</li>
              </ul>
            </div>
            <div class="box">
              <div class="text">Evening</div>
              <ul class="balls">
                <li class="resultBall ball number-part-01">9</li>
                <li class="resultBall ball number-part-02">3</li>
                <li class="resultBall ball number-part-03">0</li>
                <li class="resultBall ball number-part-04">8</li>
                <li class="resultBall ball fireball">8</li>
              </ul>
            </div>
          </div>
        </div>
        """

        rows = scraper.parse_new_jersey_pick_home(html, game="pick4")

        self.assertEqual(
            ["US-P4-NJ-PICK-4-EVENING", "US-P4-NJ-PICK-4-MIDDAY"],
            sorted(row["id"] for row in rows),
        )
        self.assertEqual(["4-7-6-1", "9-3-0-8"], sorted(row["number"] for row in rows))
        self.assertEqual(["09-05-2026", "09-05-2026"], sorted(row["date"] for row in rows))

    def test_parse_new_jersey_pick_home_reads_marker_layout_date(self):
        html = """
        <main>
          <h2>Latest NJ Pick 4 Results</h2>
          <p>Saturday, May 9, 2026</p>
          <span class="resultBall alt ball drawTime middayDraw"></span>
          <span class="resultBall">4</span><span class="resultBall">7</span>
          <span class="resultBall">6</span><span class="resultBall">1</span>
          <span class="resultBall">6</span>
          <span class="resultBall alt ball drawTime eveningDraw"></span>
          <span class="resultBall">9</span><span class="resultBall">3</span>
          <span class="resultBall">0</span><span class="resultBall">8</span>
          <span class="resultBall">8</span>
        </main>
        """

        rows = scraper.parse_new_jersey_pick_home(html, game="pick4")

        self.assertEqual(["09-05-2026", "09-05-2026"], sorted(row["date"] for row in rows))
        self.assertEqual(["4-7-6-1", "9-3-0-8"], sorted(row["number"] for row in rows))

    def test_parse_us_pick_history_page_reads_pick3_results_box_dates(self):
        html = """
        <div class="resultsBox">
          <div class="date">Friday, May 8, 2026</div>
          <div class="box"><div>Midday Draw</div>
            <span class="resultBall ball number-part-01">8719</span>
            <span class="resultBall ball number-part-02">719</span>
            <span class="resultBall ball number-part-03">19</span>
            <span class="resultBall ball fireball">9</span>
          </div>
          <div class="box"><div>Evening Draw</div>
            <span class="resultBall ball number-part-01">9203</span>
            <span class="resultBall ball number-part-02">203</span>
            <span class="resultBall ball number-part-03">03</span>
            <span class="resultBall ball fireball">3</span>
          </div>
        </div>
        """

        rows = scraper.parse_us_pick_history_page(
            html,
            game="pick3",
            state_code="FL",
            state_name="Florida",
            game_name="Pick 3",
            target_date="08-05-2026",
        )

        self.assertEqual(
            ["US-P3-FL-PICK-3-EVENING", "US-P3-FL-PICK-3-MIDDAY"],
            sorted(row["id"] for row in rows),
        )
        self.assertEqual(["8-7-1", "9-2-0"], sorted(row["number"] for row in rows))

    def test_parse_us_pick_history_page_reads_pick4_marker_dates(self):
        html = """
        <div class="drawContainer">
          <a class="date"><span>Thursday, May 7, 2026</span></a>
          <ul class="drawBalls">
            <li class="resultBall alt ball drawTime middayDraw"></li>
            <li class="resultBall alt ball number-part-01">2</li>
            <li class="resultBall alt ball number-part-02">0</li>
            <li class="resultBall alt ball number-part-03">3</li>
            <li class="resultBall alt ball number-part-04">4</li>
            <li class="resultBall alt ball fireball">7</li>
          </ul>
          <ul class="drawBalls">
            <li class="resultBall alt ball drawTime eveningDraw"></li>
            <li class="resultBall alt ball number-part-01">4</li>
            <li class="resultBall alt ball number-part-02">3</li>
            <li class="resultBall alt ball number-part-03">4</li>
            <li class="resultBall alt ball number-part-04">7</li>
            <li class="resultBall alt ball fireball">5</li>
          </ul>
        </div>
        """

        rows = scraper.parse_us_pick_history_page(
            html,
            game="pick4",
            state_code="FL",
            state_name="Florida",
            game_name="Pick 4",
            target_date="07-05-2026",
        )

        self.assertEqual(["2-0-3-4", "4-3-4-7"], sorted(row["number"] for row in rows))
        self.assertEqual(["07-05-2026", "07-05-2026"], sorted(row["date"] for row in rows))

    def test_parse_us_pick_history_page_reads_single_draw_day_states_without_label(self):
        html = """
        <div class="genBox mBottom resultsBox colHalf">
          <div class="row fx -cn -al">
            <div class="date">Friday, May 8, 2026</div>
          </div>
          <div class="box">
            <ul class="balls alt">
              <li class="resultBall ball number-part-01 medium">6</li>
              <li class="resultBall ball number-part-02 medium">9</li>
              <li class="resultBall ball number-part-03 medium">1</li>
            </ul>
          </div>
        </div>
        """

        rows = scraper.parse_us_pick_history_page(
            html,
            game="pick3",
            state_code="WA",
            state_name="Washington",
            game_name="Pick 3",
            target_date="08-05-2026",
        )

        self.assertEqual(1, len(rows))
        self.assertEqual("US-P3-WA-PICK-3-DAY", rows[0]["id"])
        self.assertEqual("6-9-1", rows[0]["number"])

    def test_parse_us_pick_history_page_reads_catalog_single_draw_states_without_label(self):
        html = """
        <div class="resultsBox">
          <div class="date">Friday, May 8, 2026</div>
          <div class="box">
            <span class="resultBall">5</span>
            <span class="resultBall">6</span>
            <span class="resultBall">1</span>
          </div>
        </div>
        """

        rows = scraper.parse_us_pick_history_page(
            html,
            game="pick3",
            state_code="MN",
            state_name="Minnesota",
            game_name="Pick 3",
            target_date="08-05-2026",
        )

        self.assertEqual(1, len(rows))
        self.assertEqual("US-P3-MN-PICK-3-DAY", rows[0]["id"])
        self.assertEqual("5-6-1", rows[0]["number"])

    def test_parse_us_pick_history_page_maps_dc_day_to_catalog_midday(self):
        html = """
        <div class="resultsBox">
          <div class="date">Friday, May 8, 2026</div>
          <div>Draw #28061</div>
          <div>Day</div><span>3</span><span>4</span><span>8</span><span>15</span>
          <div>Evening</div><span>4</span><span>6</span><span>2</span><span>12</span>
          <div>Night</div><span>0</span><span>1</span><span>7</span><span>8</span>
        </div>
        """

        rows = scraper.parse_us_pick_history_page(
            html,
            game="pick3",
            state_code="DC",
            state_name="Washington DC",
            game_name="3",
            target_date="08-05-2026",
        )

        self.assertIn("US-P3-DC-3-MIDDAY", [row["id"] for row in rows])
        self.assertIn("US-P3-DC-3-EVENING", [row["id"] for row in rows])

    def test_parse_us_pick_history_page_reads_tennessee_rows_with_no_year_date(self):
        html = """
        <div class="resultsBox">
          <div>Friday, May 8, 6:28pm</div>
          <div>Evening</div>
          <span class="resultBall">0</span><span class="resultBall">7</span>
          <span class="resultBall">8</span><span class="resultBall">7</span>
        </div>
        """

        rows = scraper.parse_us_pick_history_page(
            html,
            game="pick3",
            state_code="TN",
            state_name="Tennessee",
            game_name="Cash 3",
            target_date="08-05-2026",
        )

        self.assertEqual(1, len(rows))
        self.assertEqual("US-P3-TN-CASH-3-06-28-PM", rows[0]["id"])
        self.assertEqual("0-7-8", rows[0]["number"])

    def test_parse_us_pick_history_page_maps_wv_single_draw_to_9pm_catalog_id(self):
        html = """
        <div class="resultsBox">
          <div class="date">Friday, May 8, 2026</div>
          <span class="resultBall">7</span>
          <span class="resultBall">2</span>
          <span class="resultBall">2</span>
        </div>
        """

        rows = scraper.parse_us_pick_history_page(
            html,
            game="pick3",
            state_code="WV",
            state_name="West Virginia",
            game_name="Daily 3",
            target_date="08-05-2026",
        )

        self.assertEqual(1, len(rows))
        self.assertEqual("US-P3-WV-DAILY-3-09-00-PM", rows[0]["id"])
        self.assertEqual("7-2-2", rows[0]["number"])

    def test_sunday_pick_no_draw_rows_fill_known_closed_draws(self):
        rows = []

        scraper.append_us_pick_calendar_no_draw_rows(rows, "10-05-2026")

        ids = {row["id"] for row in rows}
        self.assertIn("US-P3-TX-PICK-3-MORNING", ids)
        self.assertIn("US-P4-TX-DAILY-4-NIGHT", ids)
        self.assertIn("US-P4-TN-CASH-4-DAY", ids)
        self.assertTrue(all(row["status"] == "no_draw" for row in rows))

    def test_pick_no_draw_calendar_does_not_add_rows_on_friday(self):
        rows = []

        scraper.append_us_pick_calendar_no_draw_rows(rows, "08-05-2026")

        self.assertEqual([], rows)

    def test_github_actions_requires_supabase_key(self):
        env = {"GITHUB_ACTIONS": "true"}

        self.assertTrue(scraper.should_fail_without_supabase_key("", env))
        self.assertFalse(scraper.should_fail_without_supabase_key("present", env))
        self.assertFalse(scraper.should_fail_without_supabase_key("", {}))

    def test_parse_miloteria_date_handles_api_formats(self):
        self.assertEqual("26-04-2026", scraper.parse_miloteria_date("Sunday, Apr 26, 2026"))
        self.assertEqual("26-04-2026", scraper.parse_miloteria_date("04/26/2026 11:00:00 PM"))

    def test_haiti_bolet_sources_are_mapped_to_catalog_ids(self):
        sources_by_id = {source["id"]: source["name"] for source in scraper.ENLOTERIA_HAITI_BOLET_SOURCES}
        self.assertEqual("Haiti Bolet 11:30 AM", sources_by_id["27"])
        self.assertEqual("Haiti Bolet 6:30 PM", sources_by_id["28"])

    def test_enloteria_sources_cover_new_catalog_ids(self):
        sources_by_id = {source["id"]: source for source in scraper.ENLOTERIA_RESULT_SOURCES}

        for lottery_id in [str(value) for value in range(29, 47)]:
            self.assertIn(lottery_id, sources_by_id)

        self.assertEqual("Georgia Día", sources_by_id["44"]["name"])
        self.assertEqual("Georgia Tarde", sources_by_id["45"]["name"])
        self.assertEqual("Georgia Noche", sources_by_id["46"]["name"])
        self.assertEqual("Anguilla 10AM", sources_by_id["2"]["source_name"])
        self.assertEqual("Anguilla 1PM", sources_by_id["4"]["source_name"])
        self.assertEqual("Anguilla 6PM", sources_by_id["11"]["source_name"])
        self.assertEqual("Anguilla 9PM", sources_by_id["14"]["source_name"])

    def test_parse_enloteria_haiti_bolet_jsonld_event(self):
        html = """
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@graph": [
            {
              "@type": "Event",
              "name": "Haiti Bolet 11:30 AM",
              "startDate": "2026-04-28T11:30:00-04:00",
              "description": "Resultados de Haiti Bolet 11:30 AM del 28 de abril de 2026. Números ganadores: 00, 54, 25."
            }
          ]
        }
        </script>
        """

        row = scraper.parse_enloteria_haiti_bolet_jsonld(
            html,
            lottery_id="27",
            lottery_name="Haiti Bolet 11:30 AM",
            target_date="28-04-2026",
        )

        self.assertEqual(
            {"id": "27", "name": "Haiti Bolet 11:30 AM", "date": "28-04-2026", "number": "00-54-25"},
            row,
        )

    def test_parse_enloteria_result_jsonld_supports_source_name_alias(self):
        html = """
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@graph": [
            {
              "@type": "Event",
              "name": "Anguilla 10AM",
              "startDate": "2026-04-28T10:00:00-04:00",
              "description": "Resultados de Anguilla 10AM. Números ganadores: 08, 14, 52."
            }
          ]
        }
        </script>
        """

        row = scraper.parse_enloteria_result_jsonld_for_dates(
            html,
            lottery_id="2",
            lottery_name="Anguila Mañana",
            target_dates=["28-04-2026"],
            source_name="Anguilla 10AM",
        )

        self.assertEqual(
            {"id": "2", "name": "Anguila Mañana", "date": "28-04-2026", "number": "08-14-52"},
            row,
        )

    def test_recent_dr_dates_include_yesterday_and_day_before(self):
        self.assertEqual(
            ["29-04-2026", "28-04-2026", "27-04-2026"],
            scraper.recent_dr_dates("29-04-2026", days_back=2),
        )

    def test_merge_results_by_id_preserves_existing_and_adds_late_haiti_bolet(self):
        existing = [
            {"id": "1", "name": "La Primera Día", "number": "01-02-03"},
            {"id": "26", "name": "New Jersey PM", "number": "11-22-33"},
        ]
        fresh = [
            {"id": "27", "name": "Haiti Bolet 11:30 AM", "number": "03-21-01"},
            {"id": "28", "name": "Haiti Bolet 6:30 PM", "number": "52-35-42"},
        ]

        merged = scraper.merge_results_by_id(existing, fresh, observed_at="2026-05-03T05:40:00Z")

        self.assertEqual(["1", "26", "27", "28"], [row["id"] for row in merged])
        self.assertEqual("2026-05-03T05:40:00Z", merged[-1]["firstSeenAt"])
        self.assertEqual("2026-05-03T05:40:00Z", merged[-1]["lastSeenAt"])
        self.assertEqual([], scraper.missing_tracked_result_ids([
            {"id": "23"},
            {"id": "24"},
            {"id": "27"},
            {"id": "28"},
        ]))

    def test_merge_results_by_id_preserves_first_seen_for_same_result(self):
        existing = [
            {
                "id": "27",
                "name": "Haiti Bolet 11:30 AM",
                "number": "03-21-01",
                "firstSeenAt": "2026-05-03T01:00:00Z",
            },
        ]
        fresh = [
            {"id": "27", "name": "Haiti Bolet 11:30 AM", "number": "03-21-01"},
        ]

        merged = scraper.merge_results_by_id(existing, fresh, observed_at="2026-05-03T05:40:00Z")

        self.assertEqual("2026-05-03T01:00:00Z", merged[0]["firstSeenAt"])
        self.assertEqual("2026-05-03T05:40:00Z", merged[0]["lastSeenAt"])

    def test_missing_tracked_result_ids_detects_haiti_gap(self):
        self.assertEqual(["27", "28"], scraper.missing_tracked_result_ids([
            {"id": "23"},
            {"id": "24"},
        ]))

    def test_merge_results_by_id_sorts_mixed_numeric_and_pick_ids(self):
        merged = scraper.merge_results_by_id(
            existing=[{"id": "US-P4-IL-PICK-4-MORNING", "number": "1-2-3-4"}],
            results=[{"id": "1", "number": "11-22-33"}],
            observed_at="2026-05-10T00:00:00Z",
        )

        self.assertEqual(["1", "US-P4-IL-PICK-4-MORNING"], [row["id"] for row in merged])

    def test_parse_enloteria_haiti_bolet_uses_recent_available_result(self):
        html = """
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@graph": [
            {
              "@type": "Event",
              "name": "Haiti Bolet 6:30 PM",
              "startDate": "2026-04-28T18:30:00-04:00",
              "description": "Resultados de Haiti Bolet 6:30 PM. Números ganadores: 12, 08, 44."
            }
          ]
        }
        </script>
        """

        row = scraper.parse_enloteria_haiti_bolet_jsonld_for_dates(
            html,
            lottery_id="28",
            lottery_name="Haiti Bolet 6:30 PM",
            target_dates=["29-04-2026", "28-04-2026", "27-04-2026"],
        )

        self.assertEqual(
            {"id": "28", "name": "Haiti Bolet 6:30 PM", "date": "28-04-2026", "number": "12-08-44"},
            row,
        )

    def test_parse_enloteria_haiti_bolet_dom_history_for_yesterday_and_day_before(self):
        html = """
        <div class="text-center">
          <h5>Haiti Bolet 11:30 AM</h5>
          <span>Martes 28 de abril, 2026</span>
          <span>11:30AM</span>
          <span>00</span><span>54</span><span>25</span>
        </div>
        <div class="text-center">
          <h5>Haiti Bolet 11:30 AM</h5>
          <span>Lunes 27 de abril, 2026</span>
          <span>11:30AM</span>
          <span>81</span><span>74</span><span>77</span>
        </div>
        """

        row = scraper.parse_enloteria_haiti_bolet_jsonld_for_dates(
            html,
            lottery_id="27",
            lottery_name="Haiti Bolet 11:30 AM",
            target_dates=["27-04-2026"],
        )

        self.assertEqual(
            {"id": "27", "name": "Haiti Bolet 11:30 AM", "date": "27-04-2026", "number": "81-74-77"},
            row,
        )

    def test_parse_enloteria_haiti_bolet_does_not_use_yesterday_as_today(self):
        html = """
        <div class="text-center">
          <h5>Haiti Bolet 11:30 AM</h5>
          <span>Miércoles 29 de abril, 2026</span>
          <span>11:30AM</span>
          <span>Avísame cuando salga</span>
        </div>
        <div class="text-center">
          <h5>Haiti Bolet 11:30 AM</h5>
          <span>Martes 28 de abril, 2026</span>
          <span>11:30AM</span>
          <span>00</span><span>54</span><span>25</span>
        </div>
        """

        row = scraper.parse_enloteria_haiti_bolet_jsonld_for_dates(
            html,
            lottery_id="27",
            lottery_name="Haiti Bolet 11:30 AM",
            target_dates=["29-04-2026"],
        )

        self.assertIsNone(row)

    def test_king_past_date_without_source_rows_becomes_no_draw(self):
        rows = scraper.build_king_no_draw_rows(
            "01-05-2026",
            seen_ids=set(),
            now_dr=datetime.datetime(2026, 5, 2, 10, 0, 0),
        )

        self.assertEqual(["23", "24"], [row["id"] for row in rows])
        self.assertEqual(["no_draw", "no_draw"], [row["status"] for row in rows])
        self.assertEqual(["", ""], [row["number"] for row in rows])

    def test_king_no_draw_does_not_override_existing_published_result(self):
        rows = scraper.build_king_no_draw_rows(
            "30-04-2026",
            seen_ids={"23", "24"},
            now_dr=datetime.datetime(2026, 5, 2, 10, 0, 0),
        )

        self.assertEqual([], rows)

    def test_king_today_without_source_rows_stays_pending_not_no_draw(self):
        rows = scraper.build_king_no_draw_rows(
            "02-05-2026",
            seen_ids=set(),
            now_dr=datetime.datetime(2026, 5, 2, 10, 0, 0),
        )

        self.assertEqual([], rows)


if __name__ == "__main__":
    unittest.main()

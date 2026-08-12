import unittest

from app.realtime import RoomBroadcaster
from app.tracker.manager import TrackerManager


class TrackerManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = TrackerManager(RoomBroadcaster())
        self.manager._packages[1]["Celeste"] = {
            "items": {100: "Key"},
            "locations": {200: "Celestial Resort A - Cassette"},
        }

    def test_printjson_renders_archipelago_categories(self) -> None:
        text, rendered = self.manager._render_printjson(
            [
                {"type": "player_id", "text": "1"},
                {"type": "text", "text": " found "},
                {"type": "item_id", "text": "100", "player": 1, "flags": 0},
                {"type": "text", "text": " at "},
                {"type": "location_id", "text": "200", "player": 1},
            ],
            {"1": {"name": "Celeste-player-1", "game": "Celeste"}},
            1,
        )
        self.assertEqual(text, "Celeste-player-1 found Key at Celestial Resort A - Cassette")
        self.assertIn('class="log-player"', rendered)
        self.assertIn('class="log-item"', rendered)
        self.assertIn('class="log-location"', rendered)

    def test_key_items_use_key_category(self) -> None:
        _, rendered = self.manager._render_printjson(
            [{"type": "item_id", "text": "100", "player": 1, "flags": 1}],
            {"1": {"name": "Celeste-player-1", "game": "Celeste"}},
            1,
        )
        self.assertIn('class="log-key"', rendered)

    def test_hint_names_are_resolved_from_data_packages(self) -> None:
        hint = self.manager._resolve_hint(
            {
                "finding_player": 1,
                "receiving_player": 1,
                "location": 200,
                "item": 100,
                "found": False,
            },
            {"1": {"name": "Celeste-player-1", "game": "Celeste"}},
            1,
        )
        self.assertEqual(hint["location"], "Celestial Resort A - Cassette")
        self.assertEqual(hint["item"], "Key")


if __name__ == "__main__":
    unittest.main()

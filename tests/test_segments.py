import unittest

from app.segments import parse_emby_segments


def chapter(ticks, *, marker="Chapter", name=""):
    return {"StartPositionTicks": ticks, "MarkerType": marker, "Name": name}


class SegmentParserTests(unittest.TestCase):
    def test_parses_all_tidb_types_and_multiple_intro_pairs(self):
        chapters = [
            chapter(10_000_000, marker="IntroStart"),
            chapter(60_000_000, marker="IntroEnd"),
            chapter(100_000_000, marker="IntroStart"),
            chapter(170_000_000, marker="IntroEnd"),
            chapter(300_000_000, marker="CreditsStart"),
            chapter(400_000_000, name="Credits End (TheIntroDB) [TheIntroDB:c1]"),
            chapter(0, name="Recap (TheIntroDB) [TheIntroDB:r1]"),
            chapter(9_000_000, name="Recap End (TheIntroDB) [TheIntroDB:r1]"),
            chapter(410_000_000, name="Preview (TheIntroDB) [TheIntroDB:p1]"),
            chapter(420_000_000, name="Preview End (TheIntroDB) [TheIntroDB:p1]"),
        ]
        result = parse_emby_segments(chapters)
        self.assertEqual([(1000, 6000), (10000, 17000)], [(x["start_ms"], x["end_ms"]) for x in result["intro"]])
        self.assertEqual((30000, 40000), (result["credits"][0]["start_ms"], result["credits"][0]["end_ms"]))
        self.assertEqual((0, 900), (result["recap"][0]["start_ms"], result["recap"][0]["end_ms"]))
        self.assertEqual((41000, 42000), (result["preview"][0]["start_ms"], result["preview"][0]["end_ms"]))

    def test_ignores_unsigned_free_text_and_duplicate_tidb_chapters(self):
        chapters = [
            chapter(1_000_000, marker="IntroStart"),
            chapter(7_000_000, marker="IntroEnd"),
            chapter(1_000_000, name="Intro (TheIntroDB) [TheIntroDB:i1]"),
            chapter(0, name="Recap"),
        ]
        result = parse_emby_segments(chapters)
        self.assertEqual(1, len(result["intro"]))
        self.assertEqual([], result["recap"])

    def test_preserves_incomplete_boundaries(self):
        result = parse_emby_segments([chapter(50_000_000, marker="IntroEnd")])
        self.assertEqual({"start_ms": None, "end_ms": 5000, "source": "emby"}, result["intro"][0])

    def test_pairs_recap_by_time_when_marker_ids_differ(self):
        result = parse_emby_segments([
            chapter(64_540_000, name="Recap (TheIntroDB) [TheIntroDB:535fee562a264f7abec732082e6e11e0]"),
            chapter(541_270_000, name="Recap End (TheIntroDB) [TheIntroDB:630c5b72ad9643f8b4ab74a9667d6c61]"),
        ])
        self.assertEqual(
            [{"start_ms": 6454, "end_ms": 54127, "source": "emby"}],
            result["recap"],
        )

    def test_pairs_multiple_preview_intervals_in_time_order(self):
        result = parse_emby_segments([
            chapter(100_000_000, name="Preview (TheIntroDB) [TheIntroDB:start-a]"),
            chapter(150_000_000, name="Preview End (TheIntroDB) [TheIntroDB:end-a]"),
            chapter(200_000_000, name="Preview (TheIntroDB) [TheIntroDB:start-b]"),
            chapter(270_000_000, name="Preview End (TheIntroDB) [TheIntroDB:end-b]"),
        ])
        self.assertEqual(
            [(10000, 15000), (20000, 27000)],
            [(value["start_ms"], value["end_ms"]) for value in result["preview"]],
        )


if __name__ == "__main__":
    unittest.main()

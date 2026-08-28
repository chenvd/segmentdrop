import unittest

from app.errors import AppError
from app.main import _validate_segments
from app.schemas import SubmitInput


def submission(segments):
    return SubmitInput.model_validate({
        "session_id": "session",
        "item_id": "item",
        "media": {"type": "episode", "tmdb_id": 1, "season": 1, "episode": 2, "duration_ms": 1_800_000},
        "segments": segments,
    })


class ValidationTests(unittest.TestCase):
    def test_optional_boundaries_are_kept_as_null(self):
        body = submission([
            {"type": "intro", "start_ms": None, "end_ms": 10_000},
            {"type": "credits", "start_ms": 1_700_000, "end_ms": None},
        ])
        self.assertEqual([
            {"type": "intro", "start_ms": None, "end_ms": 10_000},
            {"type": "credits", "start_ms": 1_700_000, "end_ms": None},
        ], _validate_segments(body, 1_800_000))

    def test_rejects_overlapping_same_type_intervals(self):
        body = submission([
            {"type": "intro", "start_ms": 0, "end_ms": 10_000},
            {"type": "intro", "start_ms": 8_000, "end_ms": 15_000},
        ])
        with self.assertRaises(AppError) as context:
            _validate_segments(body, 1_800_000)
        self.assertEqual("SEGMENT_INVALID", context.exception.code)

    def test_rejects_missing_required_boundary(self):
        body = submission([{"type": "preview", "start_ms": None, "end_ms": 10_000}])
        with self.assertRaises(AppError):
            _validate_segments(body, 1_800_000)


if __name__ == "__main__":
    unittest.main()


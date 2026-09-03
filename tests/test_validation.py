import unittest

from app.errors import AppError
from app.main import _validate_segment
from app.schemas import SubmitInput


def submission(segment):
    return SubmitInput.model_validate({
        "session_id": "session",
        "item_id": "item",
        "media": {"type": "episode", "tmdb_id": 1, "season": 1, "episode": 2, "duration_ms": 1_800_000},
        "segment": segment,
    })


class ValidationTests(unittest.TestCase):
    def test_optional_boundaries_are_kept_as_null(self):
        for segment in (
            {"type": "intro", "start_ms": None, "end_ms": 10_000},
            {"type": "credits", "start_ms": 1_700_000, "end_ms": None},
        ):
            with self.subTest(segment=segment):
                body = submission(segment)
                self.assertEqual(segment, _validate_segment(body, 1_800_000))

    def test_rejects_missing_required_boundary(self):
        body = submission({"type": "preview", "start_ms": None, "end_ms": 10_000})
        with self.assertRaises(AppError):
            _validate_segment(body, 1_800_000)


if __name__ == "__main__":
    unittest.main()

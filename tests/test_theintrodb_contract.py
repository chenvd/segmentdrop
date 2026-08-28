import json
import unittest

import httpx

from app.config import TheIntroDBSettings
from app.services import TheIntroDBService


class TheIntroDBContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_submit_uses_v3_bearer_and_null_boundaries(self):
        captured = {}

        async def handler(request: httpx.Request):
            captured["request"] = request
            return httpx.Response(201, json={"message": "accepted"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = TheIntroDBService(client)
            await service.submit(TheIntroDBSettings("secret"), {
                "tmdb_id": 1396,
                "season": 1,
                "episode": 1,
                "type": "tv",
                "segment": "credits",
                "start_ms": 3_431_000,
                "end_ms": None,
                "video_duration_ms": 3_600_000,
            })

        request = captured["request"]
        self.assertEqual("https://api.theintrodb.org/v3/submit", str(request.url))
        self.assertEqual("Bearer secret", request.headers["Authorization"])
        payload = json.loads(request.content)
        self.assertEqual("tv", payload["type"])
        self.assertEqual("credits", payload["segment"])
        self.assertIsNone(payload["end_ms"])


if __name__ == "__main__":
    unittest.main()

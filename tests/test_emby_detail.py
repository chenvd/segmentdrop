import unittest

import httpx

from app.config import EmbySettings
from app.services import EmbyService


class EmbyDetailTests(unittest.IsolatedAsyncioTestCase):
    async def test_detail_does_not_request_or_return_chapters(self):
        item_fields = []

        async def handler(request: httpx.Request):
            if request.url.path.endswith("/Sessions"):
                return httpx.Response(200, json=[{
                    "Id": "session-1",
                    "UserId": "user-1",
                    "NowPlayingItem": {"Id": "episode-1", "Type": "Episode", "SeriesId": "series-1"},
                    "PlayState": {},
                }])
            item_fields.append(request.url.params.get("Fields"))
            if request.url.path.endswith("/series-1"):
                return httpx.Response(200, json={"Id": "series-1", "Name": "剧名", "ProviderIds": {"Tmdb": "123"}})
            return httpx.Response(200, json={
                "Id": "episode-1",
                "Type": "Episode",
                "Name": "集名",
                "SeriesName": "剧名",
                "SeriesId": "series-1",
                "ParentIndexNumber": 1,
                "IndexNumber": 2,
                "RunTimeTicks": 18_000_000_000,
                "Chapters": [{"MarkerType": "IntroStart", "StartPositionTicks": 10_000_000}],
            })

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            detail = await EmbyService(client).session_detail(
                EmbySettings("http://emby.local", "secret"), "session-1", "episode-1"
            )

        self.assertNotIn("segments", detail)
        self.assertTrue(item_fields)
        self.assertTrue(all("Chapters" not in fields for fields in item_fields))


if __name__ == "__main__":
    unittest.main()

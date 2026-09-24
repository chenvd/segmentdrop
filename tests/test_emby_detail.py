import unittest

import httpx

from app.config import EmbySettings
from app.errors import AppError
from app.services import EmbyService


class EmbyDetailTests(unittest.IsolatedAsyncioTestCase):
    async def test_finished_episode_can_be_loaded_for_submission_after_autoplay(self):
        requested_items = []

        async def handler(request: httpx.Request):
            if request.url.path.endswith("/Sessions"):
                return httpx.Response(200, json=[{
                    "Id": "session-1", "UserId": "user-1",
                    "NowPlayingItem": {"Id": "episode-2", "Type": "Episode"},
                    "PlayState": {"PositionTicks": 100_000_000},
                }])
            requested_items.append(request.url.path)
            if request.url.path.endswith("/series-1"):
                return httpx.Response(200, json={"Id": "series-1", "Name": "剧名", "ProviderIds": {"Tmdb": "123"}})
            return httpx.Response(200, json={
                "Id": "episode-1", "Type": "Episode", "Name": "第一集", "SeriesId": "series-1",
                "ParentIndexNumber": 1, "IndexNumber": 1, "RunTimeTicks": 18_000_000_000,
            })

        settings = EmbySettings("http://emby.local", "secret")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = EmbyService(client)
            with self.assertRaises(AppError) as detail_error:
                await service.session_detail(settings, "session-1", "episode-1")
            self.assertEqual("SESSION_ITEM_CHANGED", detail_error.exception.code)

            detail = await service.session_detail(settings, "session-1", "episode-1", require_current=False)
            self.assertEqual("episode-1", detail["item_id"])
            self.assertEqual(123, detail["tmdb_id"])
            self.assertEqual(1, detail["episode"])
            self.assertTrue(any(path.endswith("/episode-1") for path in requested_items))

            with self.assertRaises(AppError) as position_error:
                await service.position(settings, "session-1", "episode-1")
            self.assertEqual("SESSION_ITEM_CHANGED", position_error.exception.code)

    async def test_submission_detail_accepts_stopped_session_but_checks_item_identity(self):
        async def handler(request: httpx.Request):
            if request.url.path.endswith("/Sessions"):
                return httpx.Response(200, json=[{"Id": "session-1", "UserId": "user-1"}])
            return httpx.Response(200, json={"Id": "different-item", "Type": "Movie", "ProviderIds": {"Tmdb": "123"}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(AppError) as error:
                await EmbyService(client).session_detail(
                    EmbySettings("http://emby.local", "secret"), "session-1", "movie-1", require_current=False
                )
            self.assertEqual("SESSION_ITEM_CHANGED", error.exception.code)

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

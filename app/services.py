from __future__ import annotations

import time
from typing import Any

import httpx

from .config import EmbySettings, TheIntroDBSettings
from .errors import AppError
from .segments import parse_emby_segments, ticks_to_ms


def provider_id(item: dict[str, Any], name: str) -> str | None:
    providers = item.get("ProviderIds") or {}
    for key, value in providers.items():
        if str(key).casefold() == name.casefold() and value not in (None, ""):
            return str(value)
    return None


class EmbyService:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        self._series_cache: dict[tuple[str, str, str], tuple[float, dict[str, Any]]] = {}

    async def request(
        self,
        settings: EmbySettings,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        if not settings.server_url or not settings.api_key:
            raise AppError("SETTINGS_REQUIRED", "请先配置 Emby Server URL 和 API Key。", 400)
        try:
            response = await self.client.request(
                method,
                f"{settings.server_url}/emby/{path.lstrip('/')}",
                headers={"X-Emby-Token": settings.api_key},
                params=params,
                timeout=httpx.Timeout(12, connect=4),
            )
        except httpx.RequestError as exc:
            raise AppError("EMBY_UNREACHABLE", "无法连接 Emby，请检查服务器状态。", 502) from exc
        if response.status_code in (401, 403):
            raise AppError("EMBY_UNAUTHORIZED", "Emby API Key 无效。", 401)
        if response.status_code >= 400:
            raise AppError("EMBY_UNREACHABLE", "Emby 返回了异常响应。", 502)
        return response

    async def test(self, settings: EmbySettings) -> dict[str, Any]:
        response = await self.request(settings, "GET", "System/Info/Public")
        data = response.json()
        return {"ok": True, "server_name": data.get("ServerName") or data.get("ProductName") or "Emby"}

    async def sessions(self, settings: EmbySettings) -> list[dict[str, Any]]:
        sessions = (await self.request(settings, "GET", "Sessions")).json()
        output: list[dict[str, Any]] = []
        for session in sessions if isinstance(sessions, list) else []:
            item = session.get("NowPlayingItem") or {}
            item_type = item.get("Type")
            if item_type not in {"Movie", "Episode"}:
                continue
            tmdb = provider_id(item, "tmdb")
            if item_type == "Episode":
                series = await self._series(settings, str(session.get("UserId") or ""), str(item.get("SeriesId") or ""))
                tmdb = provider_id(series, "tmdb") if series else None
            if not tmdb:
                continue
            position_ms = ticks_to_ms((session.get("PlayState") or {}).get("PositionTicks")) or 0
            duration_ms = ticks_to_ms(item.get("RunTimeTicks"))
            output.append(self._session_view(session, item, position_ms, duration_ms))
        return output

    async def session_detail(self, settings: EmbySettings, session_id: str, item_id: str) -> dict[str, Any]:
        session = await self._validated_session(settings, session_id, item_id)
        now_playing = session["NowPlayingItem"]
        user_id = str(session.get("UserId") or "")
        item = await self._item(settings, user_id, item_id)
        item_type = item.get("Type")
        if item_type not in {"Movie", "Episode"}:
            raise AppError("TMDB_ID_MISSING", "当前媒体不是可提交的电影或剧集。", 422)

        tmdb = provider_id(item, "tmdb")
        season = episode = None
        title = item.get("Name") or now_playing.get("Name") or "未命名媒体"
        episode_title = None
        if item_type == "Episode":
            series_id = str(item.get("SeriesId") or now_playing.get("SeriesId") or "")
            series = await self._series(settings, user_id, series_id)
            tmdb = provider_id(series, "tmdb") if series else None
            if not tmdb:
                raise AppError("SERIES_TMDB_ID_MISSING", "无法读取本剧的 TMDb ID。", 422)
            season = item.get("ParentIndexNumber")
            episode = item.get("IndexNumber")
            if not isinstance(season, int) or not isinstance(episode, int) or season < 1 or episode < 1:
                raise AppError("TMDB_ID_MISSING", "当前剧集缺少季或集编号。", 422)
            title = item.get("SeriesName") or series.get("Name") or "未命名剧集"
            episode_title = item.get("Name")
        elif not tmdb:
            raise AppError("TMDB_ID_MISSING", "当前电影缺少 TMDb ID。", 422)

        duration_ms = ticks_to_ms(item.get("RunTimeTicks") or now_playing.get("RunTimeTicks"))
        return {
            "session_id": session_id,
            "item_id": item_id,
            "item_type": "episode" if item_type == "Episode" else "movie",
            "title": title,
            "episode_title": episode_title,
            "season": season,
            "episode": episode,
            "year": item.get("ProductionYear"),
            "tmdb_id": int(tmdb),
            "duration_ms": duration_ms,
            "poster_url": f"/api/images/{item_id}/primary?session_id={session_id}",
            "segments": parse_emby_segments(item.get("Chapters")),
        }

    async def position(self, settings: EmbySettings, session_id: str, item_id: str) -> dict[str, Any]:
        session = await self._validated_session(settings, session_id, item_id)
        ticks = (session.get("PlayState") or {}).get("PositionTicks")
        position_ms = ticks_to_ms(ticks)
        if position_ms is None:
            raise AppError("POSITION_UNAVAILABLE", "暂时无法读取当前播放位置，请稍后重试。", 409)
        return {
            "position_ms": position_ms,
            "is_paused": bool((session.get("PlayState") or {}).get("IsPaused")),
            "device_name": session.get("DeviceName") or session.get("Client") or "当前设备",
        }

    async def image(self, settings: EmbySettings, item_id: str) -> httpx.Response:
        return await self.request(settings, "GET", f"Items/{item_id}/Images/Primary", params={"maxWidth": 500, "quality": 85})

    async def _validated_session(self, settings: EmbySettings, session_id: str, item_id: str) -> dict[str, Any]:
        data = (await self.request(settings, "GET", "Sessions", params={"Id": session_id})).json()
        sessions = data if isinstance(data, list) else []
        if not sessions:
            raise AppError("SESSION_NOT_FOUND", "当前设备已经停止播放该影片。", 404)
        session = sessions[0]
        item = session.get("NowPlayingItem")
        if not item:
            raise AppError("SESSION_STOPPED", "当前设备已经停止播放该影片。", 409)
        if str(item.get("Id")) != str(item_id):
            raise AppError("SESSION_ITEM_CHANGED", "当前播放内容已经改变，请返回正在播放页面重新选择。", 409)
        return session

    async def _item(self, settings: EmbySettings, user_id: str, item_id: str) -> dict[str, Any]:
        response = await self.request(
            settings,
            "GET",
            f"Users/{user_id}/Items/{item_id}",
            params={"Fields": "ProviderIds,Chapters,RunTimeTicks,ProductionYear"},
        )
        return response.json()

    async def _series(self, settings: EmbySettings, user_id: str, series_id: str) -> dict[str, Any]:
        if not user_id or not series_id:
            return {}
        key = (settings.server_url, user_id, series_id)
        cached = self._series_cache.get(key)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        series = await self._item(settings, user_id, series_id)
        self._series_cache[key] = (time.monotonic() + 300, series)
        if len(self._series_cache) > 512:
            now = time.monotonic()
            self._series_cache = {k: v for k, v in self._series_cache.items() if v[0] > now}
        return series

    @staticmethod
    def _session_view(session: dict[str, Any], item: dict[str, Any], position_ms: int, duration_ms: int | None) -> dict[str, Any]:
        episode = item.get("IndexNumber") if item.get("Type") == "Episode" else None
        season = item.get("ParentIndexNumber") if item.get("Type") == "Episode" else None
        progress = min(100, max(0, position_ms / duration_ms * 100)) if duration_ms else None
        return {
            "session_id": str(session.get("Id")),
            "item_id": str(item.get("Id")),
            "item_type": "episode" if item.get("Type") == "Episode" else "movie",
            "title": item.get("SeriesName") or item.get("Name") or "未命名媒体",
            "episode_title": item.get("Name") if item.get("Type") == "Episode" else None,
            "season": season,
            "episode": episode,
            "user_name": session.get("UserName") or "未知用户",
            "client": session.get("Client") or "",
            "device_name": session.get("DeviceName") or "未知设备",
            "is_paused": bool((session.get("PlayState") or {}).get("IsPaused")),
            "position_ms": position_ms,
            "duration_ms": duration_ms,
            "progress_percent": round(progress, 2) if progress is not None else None,
            "poster_url": f"/api/images/{item.get('Id')}/primary?session_id={session.get('Id')}",
        }


class TheIntroDBService:
    base_url = "https://api.theintrodb.org/v3"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def test(self, settings: TheIntroDBSettings) -> dict[str, Any]:
        if not settings.api_key:
            raise AppError("SETTINGS_REQUIRED", "请先填写 TheIntroDB API Key。", 400)
        try:
            response = await self.client.get(
                f"{self.base_url}/media",
                headers={"Authorization": f"Bearer {settings.api_key}", "Accept": "application/json"},
                params={"tmdb_id": 550},
                timeout=httpx.Timeout(15, connect=5),
            )
        except httpx.RequestError as exc:
            raise AppError("THEINTRODB_UNREACHABLE", "无法连接 TheIntroDB。", 502) from exc
        if response.status_code in (401, 403):
            raise AppError("THEINTRODB_UNAUTHORIZED", "TheIntroDB API Key 无效。", 401)
        if response.status_code >= 500:
            raise AppError("THEINTRODB_SERVER_ERROR", "TheIntroDB 服务暂时异常。", 502)
        return {"ok": True, "message": "TheIntroDB API Key 有效"}

    async def submit(self, settings: TheIntroDBSettings, payload: dict[str, Any]) -> dict[str, Any]:
        if not settings.api_key:
            raise AppError("SETTINGS_REQUIRED", "请先配置 TheIntroDB API Key。", 400)
        response = await self._request(settings, "POST", "submit", json=payload)
        try:
            body = response.json()
        except ValueError:
            body = {}
        return {"status": "success", "message": body.get("message") or "提交成功", "response": body}

    async def _request(self, settings: TheIntroDBSettings, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self.client.request(
                method,
                f"{self.base_url}/{path}",
                headers={"Authorization": f"Bearer {settings.api_key}", "Accept": "application/json"},
                timeout=httpx.Timeout(15, connect=5),
                **kwargs,
            )
        except httpx.RequestError as exc:
            raise AppError("THEINTRODB_UNREACHABLE", "无法连接 TheIntroDB。", 502) from exc
        if response.status_code in (401, 403):
            raise AppError("THEINTRODB_UNAUTHORIZED", "TheIntroDB API Key 无效。", 401)
        if response.status_code == 409:
            raise AppError("THEINTRODB_DUPLICATE", "这个分段已经提交过。", 409)
        if response.status_code in (400, 404, 422):
            detail = _response_message(response) or "TheIntroDB 拒绝了这个分段。"
            raise AppError("SEGMENT_INVALID", detail, 422)
        if response.status_code >= 500:
            raise AppError("THEINTRODB_SERVER_ERROR", "TheIntroDB 服务暂时异常。", 502)
        if response.status_code >= 400:
            raise AppError("THEINTRODB_UNREACHABLE", "TheIntroDB 返回了异常响应。", 502)
        return response


def _response_message(response: httpx.Response) -> str | None:
    try:
        data = response.json()
    except ValueError:
        return None
    if isinstance(data, dict):
        value = data.get("message") or data.get("detail") or data.get("error")
        return value if isinstance(value, str) else None
    return None

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import ConfigStore, EmbySettings, Settings, TheIntroDBSettings
from .errors import AppError
from .schemas import EmbySettingsInput, SettingsInput, SubmitInput, TheIntroDBSettingsInput
from .services import EmbyService, TheIntroDBService


ROOT = Path(__file__).resolve().parent.parent
store = ConfigStore()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(follow_redirects=True) as client:
        app.state.emby = EmbyService(client)
        app.state.theintrodb = TheIntroDBService(client)
        yield


app = FastAPI(title="SegmentDrop", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, __: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "REQUEST_INVALID", "message": "请求参数格式不正确。"}},
    )


@app.middleware("http")
async def same_origin_mutations(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if origin and urlsplit(origin).netloc != request.headers.get("host"):
            return JSONResponse(status_code=403, content={"error": {"code": "ORIGIN_REJECTED", "message": "请求来源不受信任。"}})
    return await call_next(request)


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(ROOT / "templates" / "index.html")


@app.get("/sw.js", include_in_schema=False)
async def service_worker() -> FileResponse:
    return FileResponse(
        ROOT / "static" / "sw.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
    )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/sessions")
async def sessions(request: Request) -> list[dict[str, Any]]:
    return await request.app.state.emby.sessions(store.load().emby)


@app.get("/api/sessions/{session_id}")
async def session_detail(session_id: str, item_id: str, request: Request) -> dict[str, Any]:
    return await request.app.state.emby.session_detail(store.load().emby, session_id, item_id)


@app.get("/api/sessions/{session_id}/position")
async def session_position(session_id: str, item_id: str, request: Request) -> dict[str, Any]:
    return await request.app.state.emby.position(store.load().emby, session_id, item_id)


@app.get("/api/images/{item_id}/primary")
async def image_proxy(item_id: str, request: Request) -> Response:
    upstream = await request.app.state.emby.image(store.load().emby, item_id)
    return Response(
        content=upstream.content,
        media_type=upstream.headers.get("content-type", "image/jpeg"),
        headers={"Cache-Control": "private, max-age=3600"},
    )


@app.get("/api/settings")
async def get_settings() -> dict[str, Any]:
    settings = store.load()
    return {
        "emby": {
            "server_url": settings.emby.server_url,
            "api_key_configured": bool(settings.emby.api_key),
            "api_key_masked": _masked(settings.emby.api_key),
        },
        "theintrodb": {
            "api_key_configured": bool(settings.theintrodb.api_key),
            "api_key_masked": _masked(settings.theintrodb.api_key),
        },
    }


@app.put("/api/settings")
async def put_settings(body: SettingsInput) -> dict[str, bool]:
    current = store.load()
    emby = current.emby
    tidb = current.theintrodb
    if body.emby is not None:
        emby = EmbySettings(
            server_url=body.emby.server_url.strip().rstrip("/"),
            api_key=current.emby.api_key if body.emby.api_key is None else body.emby.api_key.strip(),
        )
    if body.theintrodb is not None:
        tidb = TheIntroDBSettings(
            api_key=current.theintrodb.api_key if body.theintrodb.api_key is None else body.theintrodb.api_key.strip()
        )
    store.save(Settings(emby=emby, theintrodb=tidb))
    return {"ok": True}


@app.post("/api/settings/test-emby")
async def test_emby(body: EmbySettingsInput, request: Request) -> dict[str, Any]:
    current = store.load().emby
    candidate = EmbySettings(
        server_url=body.server_url.strip().rstrip("/"),
        api_key=current.api_key if body.api_key is None else body.api_key.strip(),
    )
    return await request.app.state.emby.test(candidate)


@app.post("/api/settings/test-theintrodb")
async def test_theintrodb(body: TheIntroDBSettingsInput, request: Request) -> dict[str, Any]:
    current = store.load().theintrodb
    candidate = TheIntroDBSettings(api_key=current.api_key if body.api_key is None else body.api_key.strip())
    return await request.app.state.theintrodb.test(candidate)


@app.post("/api/submit")
async def submit(body: SubmitInput, request: Request) -> dict[str, Any]:
    settings = store.load()
    detail = await request.app.state.emby.session_detail(
        settings.emby, body.session_id, body.item_id, require_current=False
    )
    _validate_identity(detail, body)
    segment = _validate_segment(body, detail.get("duration_ms"))
    external: dict[str, Any] = {
        "tmdb_id": detail["tmdb_id"],
        "type": "tv" if detail["item_type"] == "episode" else "movie",
        "segment": segment["type"],
        "start_ms": segment["start_ms"],
        "end_ms": segment["end_ms"],
    }
    if detail["item_type"] == "episode":
        external.update({"season": detail["season"], "episode": detail["episode"]})
    duration = detail.get("duration_ms")
    if duration is not None and 300_000 <= duration <= 21_600_000:
        external["video_duration_ms"] = duration
    try:
        result = await request.app.state.theintrodb.submit(settings.theintrodb, external)
        submitted = {"type": segment["type"], **result}
    except AppError as exc:
        status = "duplicate" if exc.code == "THEINTRODB_DUPLICATE" else "error"
        submitted = {"type": segment["type"], "status": status, "code": exc.code, "message": exc.message}
    return {"result": submitted, "submitted": 1}


def _masked(value: str) -> str | None:
    if not value:
        return None
    return "••••" + value[-4:] if len(value) >= 4 else "••••"


def _validate_identity(detail: dict[str, Any], body: SubmitInput) -> None:
    media = body.media
    values_match = (
        detail["item_id"] == body.item_id
        and detail["item_type"] == media.type
        and detail["tmdb_id"] == media.tmdb_id
        and (media.type == "movie" or (detail["season"] == media.season and detail["episode"] == media.episode))
    )
    if not values_match:
        raise AppError("SESSION_ITEM_CHANGED", "媒体信息已经改变，请重新打开详情页。", 409)


def _validate_segment(body: SubmitInput, duration_ms: int | None) -> dict[str, Any]:
    limits = {"intro": (5_000, 200_000), "recap": (5_000, 1_200_000), "credits": (5_000, 1_800_000), "preview": (5_000, 1_800_000)}
    segment = body.segment
    start, end, kind = segment.start_ms, segment.end_ms, segment.type
    if start is None and end is None:
        raise AppError("SEGMENT_INVALID", "没有可提交的分段。", 422)
    if kind in {"intro", "recap"} and end is None:
        raise AppError("SEGMENT_INVALID", f"{_segment_name(kind)}的 End 为必填项。", 422)
    if kind in {"credits", "preview"} and start is None:
        raise AppError("SEGMENT_INVALID", f"{_segment_name(kind)}的 Start 为必填项。", 422)
    effective_start = start or 0
    if end is not None and end <= effective_start:
        raise AppError("SEGMENT_INVALID", f"{_segment_name(kind)}的 End 必须晚于 Start。", 422)
    if end is not None:
        span = end - effective_start
        minimum, maximum = limits[kind]
        if not minimum <= span <= maximum:
            raise AppError("SEGMENT_INVALID", f"{_segment_name(kind)}时长必须在 {minimum // 1000}–{maximum // 1000} 秒之间。", 422)
    for value in (start, end):
        if duration_ms is not None and value is not None and value > duration_ms + 1_000:
            raise AppError("SEGMENT_INVALID", f"{_segment_name(kind)}的时间超过媒体时长。", 422)
    return {"type": kind, "start_ms": start, "end_ms": end}


def _segment_name(kind: str) -> str:
    return {"intro": "片头", "recap": "回顾", "credits": "片尾", "preview": "预告"}[kind]

"""Small local Emby fixture used for manual browser QA."""

from fastapi import FastAPI, Response

app = FastAPI()


EPISODE = {
    "Id": "episode-1",
    "Type": "Episode",
    "Name": "路障",
    "SeriesName": "羊毛战记",
    "SeriesId": "series-1",
    "IndexNumber": 6,
    "ParentIndexNumber": 2,
    "ProductionYear": 2024,
    "RunTimeTicks": 31_180_000_000,
    "ProviderIds": {"Tvdb": "demo"},
}

SESSION = {
    "Id": "session-1",
    "UserId": "user-1",
    "UserName": "Chris",
    "Client": "Emby for Apple TV",
    "DeviceName": "Apple TV 客厅",
    "NowPlayingItem": EPISODE,
    "PlayState": {"PositionTicks": 11_823_000_000, "IsPaused": True},
}


@app.get("/emby/Sessions")
async def sessions(Id: str | None = None):
    return [SESSION] if Id in (None, "session-1") else []


@app.get("/emby/Users/{user_id}/Items/{item_id}")
async def item(user_id: str, item_id: str):
    if item_id == "series-1":
        return {"Id": "series-1", "Name": "羊毛战记", "ProviderIds": {"Tmdb": "125988"}}
    return {
        **EPISODE,
        "Chapters": [
            {"StartPositionTicks": 0, "MarkerType": "Chapter", "Name": "Recap (TheIntroDB) [TheIntroDB:r1]"},
            {"StartPositionTicks": 420_000_000, "MarkerType": "Chapter", "Name": "Recap End (TheIntroDB) [TheIntroDB:r1]"},
            {"StartPositionTicks": 910_000_000, "MarkerType": "IntroStart", "Name": "Intro Start"},
            {"StartPositionTicks": 1_680_000_000, "MarkerType": "IntroEnd", "Name": "Intro End"},
            {"StartPositionTicks": 4_200_000_000, "MarkerType": "IntroStart", "Name": "Intro Start"},
            {"StartPositionTicks": 4_900_000_000, "MarkerType": "IntroEnd", "Name": "Intro End"},
            {"StartPositionTicks": 29_800_000_000, "MarkerType": "CreditsStart", "Name": "Credits Start"},
        ],
    }


@app.get("/emby/Items/{item_id}/Images/Primary")
async def image(item_id: str):
    return Response(status_code=404)


@app.get("/emby/System/Info/Public")
async def info():
    return {"ServerName": "QA Emby"}


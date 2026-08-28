from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any


@dataclass(frozen=True)
class EmbySettings:
    server_url: str = ""
    api_key: str = ""


@dataclass(frozen=True)
class TheIntroDBSettings:
    api_key: str = ""


@dataclass(frozen=True)
class Settings:
    emby: EmbySettings = EmbySettings()
    theintrodb: TheIntroDBSettings = TheIntroDBSettings()


class ConfigStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path("./data/config.json")
        self._lock = RLock()

    def load(self) -> Settings:
        with self._lock:
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                return Settings()
        return self._from_dict(raw)

    def save(self, settings: Settings) -> None:
        payload: dict[str, Any] = {
            "emby": {
                "server_url": settings.emby.server_url.rstrip("/"),
                "api_key": settings.emby.api_key,
            },
            "theintrodb": {"api_key": settings.theintrodb.api_key},
        }
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)

    @staticmethod
    def _from_dict(raw: dict[str, Any]) -> Settings:
        emby = raw.get("emby") if isinstance(raw.get("emby"), dict) else {}
        tidb = raw.get("theintrodb") if isinstance(raw.get("theintrodb"), dict) else {}
        return Settings(
            emby=EmbySettings(
                server_url=str(emby.get("server_url") or "").rstrip("/"),
                api_key=str(emby.get("api_key") or ""),
            ),
            theintrodb=TheIntroDBSettings(api_key=str(tidb.get("api_key") or "")),
        )

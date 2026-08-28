from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AppError(Exception):
    code: str
    message: str
    status_code: int = 400

    def __str__(self) -> str:
        return self.message


SETTINGS_REQUIRED = AppError("SETTINGS_REQUIRED", "请先完成服务设置。", 400)


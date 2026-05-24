from __future__ import annotations

import logging
import time
from typing import Callable

from fastapi import Request


def install_request_logging_middleware(app, logger: logging.Logger) -> None:
    @app.middleware("http")
    async def log_requests(request: Request, call_next: Callable):
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info("%s %s -> %s (%sms)", request.method, request.url.path, response.status_code, elapsed_ms)
        return response

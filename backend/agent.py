from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from livekit.agents import JobContext, WorkerOptions, cli

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = Path(__file__).resolve().parent

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / ".env.local", override=False)
load_dotenv(BACKEND_ROOT / ".env", override=False)

logger = logging.getLogger("upthrust.agent")


async def entrypoint(ctx: JobContext) -> None:
    room_name = ctx.room.name
    logger.info("AGENT_DISPATCHED room=%s", room_name)

    lk_url = os.getenv("LIVEKIT_URL", "")
    lk_key = os.getenv("LIVEKIT_API_KEY", "")
    lk_secret = os.getenv("LIVEKIT_API_SECRET", "")

    if not lk_url or not lk_key or not lk_secret:
        logger.error("Missing LIVEKIT_URL, LIVEKIT_API_KEY, or LIVEKIT_API_SECRET")
        return

    from pipecat.runner.livekit import generate_token

    pipecat_token = generate_token(
        room_name,
        f"ra-1-pipeline-{room_name}",
        lk_key,
        lk_secret,
    )

    from .call_router import run_voice_pipeline

    try:
        await run_voice_pipeline(
            room_name,
            lk_url,
            lk_key,
            lk_secret,
            token=pipecat_token,
        )
    finally:
        ctx.shutdown(reason="pipeline_ended")
        logger.info("AGENT_DONE room=%s", room_name)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            num_idle_processes=1,
        )
    )

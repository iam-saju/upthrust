from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import os

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI

from .ra1 import SessionStore
from .request_logger import install_request_logging_middleware
from .whatsapp import WhatsAppDeps, create_whatsapp_router

load_dotenv()
load_dotenv(".env.local", override=False)

logger = logging.getLogger("upthrust.backend")
if not logger.handlers:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def create_meta_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=15.0))

def create_sarvam_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=15.0))


def create_airtable_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=15.0))


def get_meta_client(app: FastAPI) -> httpx.AsyncClient:
    return app.state.meta_client


def get_sarvam_client(app: FastAPI) -> httpx.AsyncClient:
    return app.state.sarvam_client


def get_airtable_client(app: FastAPI) -> httpx.AsyncClient:
    return app.state.airtable_client


def get_session_store(app: FastAPI) -> SessionStore:
    return app.state.session_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Keep Groq env readiness separate from runtime usage for now.
    # Pipecat remains deferred for WhatsApp because delivery still requires a complete audio file.
    app.state.meta_client = create_meta_client()
    app.state.sarvam_client = create_sarvam_client()
    app.state.airtable_client = create_airtable_client()
    app.state.session_store = SessionStore()
    try:
        yield
    finally:
        await app.state.meta_client.aclose()
        await app.state.sarvam_client.aclose()
        await app.state.airtable_client.aclose()


app = FastAPI(title="Upthrust WhatsApp Backend", lifespan=lifespan)
install_request_logging_middleware(app, logger)
app.include_router(
    create_whatsapp_router(
        WhatsAppDeps(
            logger=logger,
            meta_client_getter=lambda: get_meta_client(app),
            sarvam_client_getter=lambda: get_sarvam_client(app),
            airtable_client_getter=lambda: get_airtable_client(app),
            session_store_getter=lambda: get_session_store(app),
        )
    )
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI

from .call_router import CallDeps, create_call_router
from .conversation import DirectSessionStore
from .twilio import router as twilio_router
from .request_logger import install_request_logging_middleware
from .voice_session import CallSessionStore
from .whatsapp import WhatsAppDeps, create_whatsapp_router

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = Path(__file__).resolve().parent

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / ".env.local", override=False)
load_dotenv(BACKEND_ROOT / ".env", override=False)

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


def create_groq_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=15.0))


def create_airtable_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=15.0))


def get_meta_client(app: FastAPI) -> httpx.AsyncClient:
    return app.state.meta_client


def get_sarvam_client(app: FastAPI) -> httpx.AsyncClient:
    return app.state.sarvam_client


def get_groq_client(app: FastAPI) -> httpx.AsyncClient:
    return app.state.groq_client


def get_airtable_client(app: FastAPI) -> httpx.AsyncClient:
    return app.state.airtable_client


def get_direct_session_store(app: FastAPI) -> DirectSessionStore:
    return app.state.direct_session_store

def get_call_session_store(app: FastAPI) -> CallSessionStore:
    return app.state.call_session_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.meta_client = create_meta_client()
    app.state.sarvam_client = create_sarvam_client()
    app.state.groq_client = create_groq_client()
    app.state.airtable_client = create_airtable_client()
    app.state.direct_session_store = DirectSessionStore()
    app.state.call_session_store = CallSessionStore()
    try:
        yield
    finally:
        await app.state.meta_client.aclose()
        await app.state.sarvam_client.aclose()
        await app.state.groq_client.aclose()
        await app.state.airtable_client.aclose()


app = FastAPI(title="Upthrust WhatsApp Backend", lifespan=lifespan)
install_request_logging_middleware(app, logger)
app.include_router(
    create_whatsapp_router(
        WhatsAppDeps(
            logger=logger,
            meta_client_getter=lambda: get_meta_client(app),
            sarvam_client_getter=lambda: get_sarvam_client(app),
            groq_client_getter=lambda: get_groq_client(app),
            airtable_client_getter=lambda: get_airtable_client(app),
            direct_session_store_getter=lambda: get_direct_session_store(app),
        )
    )
)
app.include_router(
    create_call_router(
        CallDeps(
            logger=logger,
            airtable_client_getter=lambda: get_airtable_client(app),
        )
    )
)
app.include_router(twilio_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

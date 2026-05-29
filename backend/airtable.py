from __future__ import annotations

import os
import re
from typing import Any, Protocol

import httpx


class WaitlistProfile(Protocol):
    name: str
    email: str
    phone: str
    business: str
    support_calls: str
    question: str


class WaitlistSession(Protocol):
    profile: WaitlistProfile


def airtable_api_key() -> str | None:
    return os.getenv("AIRTABLE_API_KEY")


def airtable_base_id() -> str | None:
    return os.getenv("AIRTABLE_BASE_ID")


def airtable_waitlist_table() -> str:
    return os.getenv("AIRTABLE_WAITLIST_TABLE_NAME", os.getenv("AIRTABLE_SETUP_TABLE_NAME", "waitinlist"))


def require_airtable_config() -> tuple[str, str, str]:
    api_key = airtable_api_key()
    base_id = airtable_base_id()
    table_name = airtable_waitlist_table()
    missing = []
    if not api_key:
        missing.append("AIRTABLE_API_KEY")
    if not base_id:
        missing.append("AIRTABLE_BASE_ID")
    if missing:
        raise RuntimeError(f"Missing Airtable environment variables: {', '.join(missing)}")
    return api_key, base_id, table_name


def airtable_url() -> str:
    _, base_id, table_name = require_airtable_config()
    return f"https://api.airtable.com/v0/{base_id}/{table_name}"


def format_waitlist_business(profile: WaitlistProfile) -> str:
    parts = []
    if profile.business:
        parts.append(f"Business: {profile.business}")
    if profile.support_calls:
        parts.append(f"Support calls: {profile.support_calls}")
    return " | ".join(parts)


async def find_waitlist_caller(
    *,
    client: httpx.AsyncClient,
    phone: str,
    name: str = "",
) -> dict[str, Any] | None:
    api_key, _, _ = require_airtable_config()
    normalized_phone = "".join(ch for ch in phone if ch.isdigit())
    response = await client.get(
        airtable_url(),
        headers={"Authorization": f"Bearer {api_key}"},
        params={"filterByFormula": f"{{phone no}} = {normalized_phone}"},
    )
    response.raise_for_status()
    records = response.json().get("records") or []
    if records:
        return _fields_with_record_id(records[0])
    if name:
        return await find_waitlist_caller_by_name(client=client, name=name)
    return None


async def find_waitlist_caller_by_name(
    *,
    client: httpx.AsyncClient,
    name: str,
) -> dict[str, Any] | None:
    api_key, _, _ = require_airtable_config()
    normalized_name = " ".join((name or "").strip().lower().split())
    if not normalized_name:
        return None
    formulas = [
        f"TRIM(LOWER({{name}})) = {_airtable_string(normalized_name)}",
        f"FIND({_airtable_string(normalized_name)}, TRIM(LOWER({{name}}))) > 0",
    ]
    for formula in formulas:
        response = await client.get(
            airtable_url(),
            headers={"Authorization": f"Bearer {api_key}"},
            params={"filterByFormula": formula},
        )
        response.raise_for_status()
        records = response.json().get("records") or []
        if records:
            return _fields_with_record_id(records[0])
    return None


def waitlist_business_from_record(record: dict[str, Any]) -> str:
    aliases = {
        _normalize_airtable_field_name("whats your use"),
        _normalize_airtable_field_name("what's your use"),
        _normalize_airtable_field_name("what is your use"),
        _normalize_airtable_field_name("aim of your project"),
        _normalize_airtable_field_name("business"),
    }
    for key, value in record.items():
        normalized_key = _normalize_airtable_field_name(str(key))
        if normalized_key in aliases and value:
            return str(value).strip()
    return ""


def _airtable_string(value: str) -> str:
    return "'" + value.replace("'", "\\'") + "'"


def _normalize_airtable_field_name(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", value.strip().lower())
    return " ".join(cleaned.split())


async def add_waitlist_caller(*, client: httpx.AsyncClient, session: WaitlistSession) -> dict[str, Any]:
    api_key, _, _ = require_airtable_config()
    normalized_phone = "".join(ch for ch in session.profile.phone if ch.isdigit())
    fields = {
        "name": session.profile.name,
        "mail": session.profile.email,
        "phone no": int(normalized_phone) if normalized_phone else 0,
        "aim of your project": format_waitlist_business(session.profile),
        "Question": session.profile.question,
    }
    response = await client.post(
        airtable_url(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"fields": fields},
    )
    response.raise_for_status()
    return response.json()


async def create_waitlist_lead(
    *,
    client: httpx.AsyncClient,
    name: str,
    phone: str,
    business_use: str,
    question: str = "",
) -> dict[str, Any]:
    api_key, _, _ = require_airtable_config()
    fields = _lead_fields(name=name, phone=phone, business_use=business_use, question=question)
    response = await client.post(
        airtable_url(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"fields": fields},
    )
    response.raise_for_status()
    return response.json()


async def update_waitlist_lead(
    *,
    client: httpx.AsyncClient,
    record_id: str,
    name: str,
    phone: str,
    business_use: str,
    question: str = "",
) -> dict[str, Any]:
    api_key, _, _ = require_airtable_config()
    fields = _lead_fields(name=name, phone=phone, business_use=business_use, question=question)
    response = await client.patch(
        f"{airtable_url()}/{record_id}",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"fields": fields},
    )
    response.raise_for_status()
    return response.json()


def _lead_fields(*, name: str, phone: str, business_use: str, question: str = "") -> dict[str, Any]:
    normalized_phone = "".join(ch for ch in phone if ch.isdigit())
    fields: dict[str, Any] = {
        "name": name,
        "phone no": int(normalized_phone) if normalized_phone else 0,
        "whats your use": business_use,
    }
    if question:
        fields["Question"] = question
    return fields


def _fields_with_record_id(record: dict[str, Any]) -> dict[str, Any]:
    fields = dict(record.get("fields") or {})
    record_id = record.get("id")
    if record_id:
        fields["_record_id"] = record_id
    return fields

import os
import re

import httpx
from fastapi import HTTPException


SUPABASE_AUTH_EMAIL_DOMAIN = os.getenv("SUPABASE_AUTH_EMAIL_DOMAIN", "auth.findx.local")


def _get_supabase_url() -> str:
    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    if not supabase_url:
        raise HTTPException(status_code=500, detail="SUPABASE_URL is not configured")
    return supabase_url


def _get_anon_key() -> str:
    anon_key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_PUBLISHABLE_KEY")
    if not anon_key:
        raise HTTPException(status_code=500, detail="Supabase public auth key is not configured")
    return anon_key


def _get_service_role_key() -> str:
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not service_role_key:
        raise HTTPException(status_code=500, detail="SUPABASE_SERVICE_ROLE_KEY is not configured")
    return service_role_key


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", (phone or "").strip())
    if not digits:
        return ""
    if digits.startswith("0"):
        return "92" + digits[1:]
    if digits.startswith("92"):
        return digits
    return "92" + digits


def build_phone_variants(phone: str) -> list[str]:
    normalized = normalize_phone(phone)
    variants: list[str] = []
    for candidate in [phone, normalized, f"0{normalized[2:]}" if normalized.startswith("92") else normalized]:
        if candidate and candidate not in variants:
            variants.append(candidate)
    return variants


def phone_login_email(phone: str) -> str:
    normalized = normalize_phone(phone)
    if not normalized:
        raise HTTPException(status_code=400, detail="Phone number is required")
    return f"{normalized}@{SUPABASE_AUTH_EMAIL_DOMAIN}"


def extract_phone_from_auth_user(auth_user: dict) -> str:
    user_metadata = auth_user.get("user_metadata") or {}
    phone = user_metadata.get("phone") or auth_user.get("phone")
    if phone:
        return normalize_phone(phone)

    email = (auth_user.get("email") or "").strip().lower()
    if "@" in email:
        local_part, _, domain = email.partition("@")
        if domain == SUPABASE_AUTH_EMAIL_DOMAIN:
            return normalize_phone(local_part)
    return ""


def _response_message(response: httpx.Response, fallback: str) -> str:
    try:
        payload = response.json()
    except ValueError:
        return fallback

    if isinstance(payload, dict):
        return (
            payload.get("msg")
            or payload.get("message")
            or payload.get("error_description")
            or payload.get("error")
            or fallback
        )
    return fallback


async def create_auth_user(*, phone: str, password: str, name: str, role: str) -> dict:
    service_role_key = _get_service_role_key()
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            f"{_get_supabase_url()}/auth/v1/admin/users",
            headers={
                "apikey": service_role_key,
                "Authorization": f"Bearer {service_role_key}",
                "Content-Type": "application/json",
            },
            json={
                "email": phone_login_email(phone),
                "password": password,
                "email_confirm": True,
                "user_metadata": {
                    "name": name,
                    "phone": normalize_phone(phone),
                    "role": role,
                },
                "app_metadata": {
                    "role": role,
                },
            },
        )

    if response.status_code not in {200, 201}:
        raise HTTPException(
            status_code=400,
            detail=_response_message(response, "Failed to create Supabase auth user"),
        )

    payload = response.json()
    return payload.get("user") if isinstance(payload, dict) and payload.get("user") else payload


async def sign_in_with_phone(phone: str, password: str) -> dict:
    anon_key = _get_anon_key()
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            f"{_get_supabase_url()}/auth/v1/token?grant_type=password",
            headers={
                "apikey": anon_key,
                "Content-Type": "application/json",
            },
            json={
                "email": phone_login_email(phone),
                "password": password,
            },
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=401,
            detail=_response_message(response, "Invalid credentials"),
        )

    return response.json()


async def get_auth_user(token: str) -> dict:
    anon_key = _get_anon_key()
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            f"{_get_supabase_url()}/auth/v1/user",
            headers={
                "apikey": anon_key,
                "Authorization": f"Bearer {token}",
            },
        )

    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return response.json()


async def update_auth_user_password(user_id: str, password: str) -> dict:
    service_role_key = _get_service_role_key()
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.put(
            f"{_get_supabase_url()}/auth/v1/admin/users/{user_id}",
            headers={
                "apikey": service_role_key,
                "Authorization": f"Bearer {service_role_key}",
                "Content-Type": "application/json",
            },
            json={
                "password": password,
            },
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail=_response_message(response, "Failed to update Supabase password"),
        )

    payload = response.json()
    return payload.get("user") if isinstance(payload, dict) and payload.get("user") else payload


async def find_auth_user_by_phone(phone: str) -> dict | None:
    """Look up a Supabase Auth user by their phone-derived email (admin API)."""
    service_role_key = _get_service_role_key()
    email = phone_login_email(phone)
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            f"{_get_supabase_url()}/auth/v1/admin/users",
            headers={
                "apikey": service_role_key,
                "Authorization": f"Bearer {service_role_key}",
            },
            params={"filter": email, "page": 1, "per_page": 10},
        )
    if response.status_code != 200:
        return None
    data = response.json()
    users = data.get("users", []) if isinstance(data, dict) else data
    for u in users:
        if (u.get("email") or "").lower() == email.lower():
            return u
    return None
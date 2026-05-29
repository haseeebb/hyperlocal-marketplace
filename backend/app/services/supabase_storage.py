import mimetypes
import os
import uuid

import httpx
from fastapi import HTTPException

# Module-level flag so we only check/create the bucket once per process startup
_bucket_ensured: bool = False


def _get_supabase_url() -> str:
    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    if not supabase_url:
        raise HTTPException(status_code=500, detail="SUPABASE_URL is not configured")
    return supabase_url


def _get_service_role_key() -> str:
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not service_role_key:
        raise HTTPException(status_code=500, detail="SUPABASE_SERVICE_ROLE_KEY is not configured")
    return service_role_key


def _get_bucket_name() -> str:
    return os.getenv("SUPABASE_STORAGE_BUCKET", "listing-images")


def _build_headers(content_type: str | None = None) -> dict[str, str]:
    headers = {
        "apikey": _get_service_role_key(),
        "Authorization": f"Bearer {_get_service_role_key()}",
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


async def ensure_public_bucket_exists(client: httpx.AsyncClient) -> None:
    global _bucket_ensured
    if _bucket_ensured:
        return

    bucket_name = _get_bucket_name()
    response = await client.get(
        f"{_get_supabase_url()}/storage/v1/bucket/{bucket_name}",
        headers=_build_headers(),
    )

    if response.status_code == 200:
        _bucket_ensured = True
        return

    # Supabase returns 400 or 404 when the bucket doesn't exist
    if response.status_code not in {400, 404}:
        raise HTTPException(status_code=500, detail="Failed to inspect Supabase storage bucket")

    create_response = await client.post(
        f"{_get_supabase_url()}/storage/v1/bucket",
        headers=_build_headers("application/json"),
        json={
            "id": bucket_name,
            "name": bucket_name,
            "public": True,
        },
    )
    if create_response.status_code not in {200, 201}:
        raise HTTPException(status_code=500, detail="Failed to create Supabase storage bucket")

    _bucket_ensured = True


def _infer_file_extension(content_type: str | None) -> str:
    guessed = mimetypes.guess_extension(content_type or "") or ".jpg"
    return guessed if guessed.startswith(".") else f".{guessed}"


async def upload_public_image(content: bytes, content_type: str | None = None) -> str:
    bucket_name = _get_bucket_name()
    file_extension = _infer_file_extension(content_type)
    object_path = f"whatsapp/{uuid.uuid4().hex}{file_extension}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        await ensure_public_bucket_exists(client)
        upload_response = await client.post(
            f"{_get_supabase_url()}/storage/v1/object/{bucket_name}/{object_path}",
            headers={
                **_build_headers(content_type or "application/octet-stream"),
                "x-upsert": "false",
            },
            content=content,
        )

    if upload_response.status_code not in {200, 201}:
        raise HTTPException(status_code=500, detail="Failed to upload image to Supabase storage")

    return f"{_get_supabase_url()}/storage/v1/object/public/{bucket_name}/{object_path}"
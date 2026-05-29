from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.models import Store, User
from app.routes.auth import get_current_local_user, get_local_user_by_phone
from app.services.supabase_auth import create_auth_user, normalize_phone
from pydantic import BaseModel
from typing import Optional
import uuid
import re

router = APIRouter()


class StoreCreate(BaseModel):
    name: str
    description: Optional[str] = None
    category: str
    city: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    whatsapp_number: str
    owner_phone: str
    owner_name: str
    password: Optional[str] = None


# ── Register a new store ─────────────────────────────
@router.post("/register")
async def register_store(data: StoreCreate, db: AsyncSession = Depends(get_db)):
    
    # Normalize whatsapp number to 92 format, strip non-digits
    wa_phone = normalize_phone(data.whatsapp_number)
    phone_variants = [wa_phone, '0' + wa_phone[2:]]

    for p in phone_variants:
        result = await db.execute(
            select(Store).where(
                Store.whatsapp_number == p,
                Store.is_active == True
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail="A store is already registered with this WhatsApp number. Each number can only have one store."
            )

    # Find or create user
    owner_phone = normalize_phone(data.owner_phone)
    user = await get_local_user_by_phone(db, owner_phone)

    if not user:
        if not data.password:
            raise HTTPException(status_code=400, detail="Password is required to create a seller account")

        auth_user = await create_auth_user(
            phone=owner_phone,
            password=data.password,
            name=data.owner_name,
            role="seller",
        )
        user = User(
            phone=owner_phone,
            supabase_user_id=auth_user["id"],
            name=data.owner_name,
            role="seller",
        )
        db.add(user)
        await db.flush()
    else:
        user.role = "seller"
        if not user.supabase_user_id and data.password:
            auth_user = await create_auth_user(
                phone=user.phone,
                password=data.password,
                name=user.name or data.owner_name,
                role="seller",
            )
            user.supabase_user_id = auth_user["id"]

    store = Store(
        owner_id=user.id,
        name=data.name,
        description=data.description,
        category=data.category,
        city=data.city,
        lat=data.lat,
        lng=data.lng,
        whatsapp_number=wa_phone,
        is_verified=False
    )
    db.add(store)
    await db.commit()
    return {"message": "Store submitted for review", "store_id": str(store.id)}
# ── Debug endpoint ───────────────────────────────────
@router.get("/test-my")
async def test_my_store(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
):
    try:
        user = await get_current_local_user(authorization, db)
        result2 = await db.execute(select(Store).where(Store.owner_id == user.id))
        store = result2.scalar_one_or_none()
        return {
            "user_id": str(user.id),
            "phone": user.phone,
            "role": user.role,
            "store_found": store is not None,
            "store_name": store.name if store else None
        }
    except Exception as e:
        return {"error": str(e)}

# ── Get seller's own store (requires JWT) ────────────
@router.get("/my")
async def get_my_store(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
):
    user = await get_current_local_user(authorization, db)

    # Try 1: find by owner_id + verified + active
    result = await db.execute(
        select(Store).where(
            Store.owner_id == user.id,
            Store.is_active == True,
            Store.is_verified == True
        ).limit(1)
    )
    store = result.scalar_one_or_none()

    # Try 2: find by owner_id + active only
    if not store:
        result = await db.execute(
            select(Store).where(
                Store.owner_id == user.id,
                Store.is_active == True
            ).limit(1)
        )
        store = result.scalar_one_or_none()

    # Try 3: find by phone number + active
    if not store:
        result = await db.execute(
            select(Store).where(
                Store.whatsapp_number == user.phone,
                Store.is_active == True
            ).limit(1)
        )
        store = result.scalar_one_or_none()

    # Try 4: find by phone with country code variations
    if not store:
        phone_variants = [
            user.phone,
            '92' + user.phone.lstrip('0'),
            '0' + user.phone.lstrip('92') if user.phone.startswith('92') else user.phone
        ]
        for phone in phone_variants:
            result = await db.execute(
                select(Store).where(
                    Store.whatsapp_number == phone,
                    Store.is_active == True
                ).limit(1)
            )
            store = result.scalar_one_or_none()
            if store:
                break

    if not store:
        raise HTTPException(status_code=404, detail=f"No store found for user {user.id}, phone {user.phone}")

    return {
        "id":                 str(store.id),
        "name":               store.name,
        "description":        store.description,
        "category":           store.category or None,
        "city":               store.city,
        "lat":                float(store.lat) if store.lat else None,
        "lng":                float(store.lng) if store.lng else None,
        "whatsapp_number":    store.whatsapp_number,
        "is_verified":        store.is_verified,
        "is_active":          store.is_active,
        "delivery_available": False,
    }

# ── Get store by ID (public) ─────────────────────────
@router.get("/{store_id}")
async def get_store(store_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Store).where(
            Store.id == uuid.UUID(store_id),
            Store.is_active == True
        )
    )
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return {
        "id":              str(store.id),
        "name":            store.name,
        "description":     store.description,
        "category":        store.category or None,
        "city":            store.city,
        "lat":             float(store.lat) if store.lat else None,
        "lng":             float(store.lng) if store.lng else None,
        "whatsapp_number": store.whatsapp_number,
        "is_verified":     store.is_verified,
    }
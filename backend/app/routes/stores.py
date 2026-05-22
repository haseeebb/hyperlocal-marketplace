from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.models import Store, User
from app.routes.auth import verify_token
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
    wa_phone = re.sub(r'\D', '', data.whatsapp_number.strip())
    if wa_phone.startswith('0'):
        wa_phone = '92' + wa_phone[1:]
    elif not wa_phone.startswith('92'):
        wa_phone = '92' + wa_phone
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
    result = await db.execute(select(User).where(User.phone == data.owner_phone))
    user = result.scalar_one_or_none()

    if not user:
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        hashed = pwd_context.hash(data.password) if data.password else None
        user = User(
            phone=data.owner_phone,
            name=data.owner_name,
            role="seller",
            hashed_password=hashed
        )
        db.add(user)
        await db.flush()
    else:
        if data.password and not user.hashed_password:
            from passlib.context import CryptContext
            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
            user.hashed_password = pwd_context.hash(data.password)
        user.role = "seller"

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
# ── Get seller's own store (requires JWT) ────────────
@router.get("/my")
async def get_my_store(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Login required")

    token = authorization.split(" ")[1]
    payload = verify_token(token)
    user_id = payload.get("sub")

    # Find user by ID
    result = await db.execute(
        select(User).where(User.id == uuid.UUID(user_id))
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

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
        raise HTTPException(status_code=404, detail=f"No store found for user {user_id}, phone {user.phone}")

    return {
        "id":                 str(store.id),
        "name":               store.name,
        "description":        store.description,
        "category":           store.category.value if store.category else None,
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
        "category":        store.category.value if store.category else None,
        "city":            store.city,
        "lat":             float(store.lat) if store.lat else None,
        "lng":             float(store.lng) if store.lng else None,
        "whatsapp_number": store.whatsapp_number,
        "is_verified":     store.is_verified,
    }
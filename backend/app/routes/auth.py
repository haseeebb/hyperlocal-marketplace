from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.models import Store, User
from app.services.supabase_auth import (
    build_phone_variants,
    create_auth_user,
    extract_phone_from_auth_user,
    find_auth_user_by_phone,
    get_auth_user,
    normalize_phone,
    sign_in_with_phone,
    update_auth_user_password,
)
from pydantic import BaseModel
from typing import Optional
from passlib.context import CryptContext
import os

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ADMIN_BOOTSTRAP_SECRET = os.getenv("ADMIN_BOOTSTRAP_SECRET")

# ── Schemas ───────────────────────────────────────────
class LoginSchema(BaseModel):
    phone: str
    password: str

class AdminCreate(BaseModel):
    phone: str
    name: str
    password: str

class BuyerCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: str
    address: Optional[str] = None
    password: str
    role: Optional[str] = "buyer"

class SetPassword(BaseModel):
    phone: str
    new_password: str

# ── Helpers ───────────────────────────────────────────
async def get_local_user_by_phone(db: AsyncSession, phone: str) -> Optional[User]:
    variants = build_phone_variants(phone)
    result = await db.execute(select(User).where(User.phone.in_(variants)))
    users = result.scalars().all()
    normalized = normalize_phone(phone)

    for user in users:
        if normalize_phone(user.phone) == normalized:
            return user
    return users[0] if users else None


async def sync_store_owner(db: AsyncSession, user: User):
    for phone in build_phone_variants(user.phone):
        result = await db.execute(select(Store).where(Store.whatsapp_number == phone))
        store = result.scalar_one_or_none()
        if store and store.owner_id != user.id:
            store.owner_id = user.id
            await db.flush()
            return


async def ensure_local_user(db: AsyncSession, auth_user: dict, fallback_role: str = "buyer") -> User:
    result = await db.execute(select(User).where(User.supabase_user_id == auth_user["id"]))
    local_user = result.scalar_one_or_none()

    phone = extract_phone_from_auth_user(auth_user)
    if not phone:
        raise HTTPException(status_code=400, detail="Supabase user is missing phone metadata")

    if not local_user:
        local_user = await get_local_user_by_phone(db, phone)

    user_metadata = auth_user.get("user_metadata") or {}
    app_metadata = auth_user.get("app_metadata") or {}
    role = app_metadata.get("role") or user_metadata.get("role") or (local_user.role if local_user else fallback_role)
    name = user_metadata.get("name") or (local_user.name if local_user else None) or phone

    if not local_user:
        local_user = User(
            phone=phone,
            supabase_user_id=auth_user["id"],
            name=name,
            role=role,
        )
        db.add(local_user)
    else:
        local_user.phone = phone
        local_user.supabase_user_id = auth_user["id"]
        local_user.name = name
        local_user.role = role

    await db.flush()
    await sync_store_owner(db, local_user)
    return local_user


async def verify_token(token: str):
    auth_user = await get_auth_user(token)
    return {
        "sub": auth_user["id"],
        "role": (auth_user.get("app_metadata") or {}).get("role"),
        "auth_user": auth_user,
    }


async def get_current_local_user(
    authorization: Optional[str],
    db: AsyncSession,
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Login required")

    payload = await verify_token(authorization.split(" ")[1])
    local_user = await ensure_local_user(db, payload["auth_user"])
    await db.commit()
    return local_user

# ── CREATE ADMIN (run once) ───────────────────────────
@router.post("/create-admin")
async def create_admin(
    data: AdminCreate,
    db: AsyncSession = Depends(get_db),
    bootstrap_secret: Optional[str] = Header(None, alias="X-Admin-Bootstrap-Secret"),
):
    if not ADMIN_BOOTSTRAP_SECRET or bootstrap_secret != ADMIN_BOOTSTRAP_SECRET:
        raise HTTPException(status_code=403, detail="Admin bootstrap is disabled")

    phone = normalize_phone(data.phone)
    if await get_local_user_by_phone(db, phone):
        raise HTTPException(status_code=400, detail="User already exists")

    # Try to create the Supabase Auth user; if it already exists (from a
    # previous failed attempt), look it up instead.
    try:
        auth_user = await create_auth_user(
            phone=phone,
            password=data.password,
            name=data.name,
            role="admin",
        )
    except HTTPException as exc:
        if "already been registered" in str(exc.detail):
            auth_user = await find_auth_user_by_phone(phone)
            if not auth_user:
                raise HTTPException(status_code=500, detail="Auth user exists but could not be retrieved")
        else:
            raise

    user = User(
        phone=phone,
        supabase_user_id=auth_user["id"],
        name=data.name,
        role="admin",
    )
    db.add(user)
    await db.commit()
    return {"message": "Admin created successfully"}

# ── REGISTER BUYER ────────────────────────────────────
@router.post("/register-buyer")
async def register_buyer(data: BuyerCreate, db: AsyncSession = Depends(get_db)):
    phone = normalize_phone(data.phone)
    if await get_local_user_by_phone(db, phone):
        raise HTTPException(status_code=400, detail="User already exists with this phone number")
    auth_user = await create_auth_user(
        phone=phone,
        password=data.password,
        name=data.name,
        role="buyer",
    )
    user = User(
        phone=phone,
        supabase_user_id=auth_user["id"],
        name=data.name,
        role="buyer",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"id": str(user.id), "message": "Buyer account created", "name": user.name}

# ── LOGIN ─────────────────────────────────────────────
@router.post("/login")
async def login(data: LoginSchema, db: AsyncSession = Depends(get_db)):
    phone = normalize_phone(data.phone)
    local_user = await get_local_user_by_phone(db, phone)

    try:
        session = await sign_in_with_phone(phone, data.password)
    except HTTPException:
        if not local_user or not local_user.hashed_password or not pwd_context.verify(data.password, local_user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        if local_user.supabase_user_id:
            await update_auth_user_password(local_user.supabase_user_id, data.password)
        else:
            auth_user = await create_auth_user(
                phone=phone,
                password=data.password,
                name=local_user.name or phone,
                role=local_user.role,
            )
            local_user.supabase_user_id = auth_user["id"]
            await db.commit()

        session = await sign_in_with_phone(phone, data.password)

    auth_user = session.get("user") or await get_auth_user(session["access_token"])
    local_user = await ensure_local_user(
        db,
        auth_user,
        fallback_role=local_user.role if local_user else "buyer",
    )
    await db.commit()

    return {
        "access_token": session["access_token"],
        "refresh_token": session.get("refresh_token"),
        "token_type":   "bearer",
        "name":         local_user.name,
        "role":         local_user.role,
    }

# ── SET / RESET PASSWORD ──────────────────────────────
@router.post("/set-password")
async def set_password(
    data: SetPassword,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_local_user(authorization, db)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    normalized_phone = normalize_phone(data.phone)
    if normalize_phone(user.phone) != normalized_phone:
        raise HTTPException(status_code=403, detail="You can only update your own password")

    if user.supabase_user_id:
        await update_auth_user_password(user.supabase_user_id, data.new_password)
    else:
        auth_user = await create_auth_user(
            phone=user.phone,
            password=data.new_password,
            name=user.name or user.phone,
            role=user.role,
        )
        user.supabase_user_id = auth_user["id"]

    user.hashed_password = None
    await db.commit()
    return {"message": f"Password updated for {user.name}"}

# ── GET CURRENT USER (token required) ─────────────────
@router.get("/me")
async def get_me(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
):
    user = await get_current_local_user(authorization, db)
    return {
        "id":   str(user.id),
        "name": user.name,
        "role": user.role,
        "phone": user.phone
    }

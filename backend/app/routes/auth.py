from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.models import User
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext
import os

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY  = os.getenv("SECRET_KEY", "changeme_minimum_32_characters_long")
ALGORITHM   = "HS256"

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
def create_token(user_id: str, role: str):
    payload = {
        "sub": user_id,
        "role": role,
        "exp": datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

# ── CREATE ADMIN (run once) ───────────────────────────
@router.post("/create-admin")
async def create_admin(data: AdminCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.phone == data.phone))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User already exists")
    user = User(
        phone=data.phone,
        name=data.name,
        role="admin",
        hashed_password=pwd_context.hash(data.password)
    )
    db.add(user)
    await db.commit()
    return {"message": "Admin created successfully"}

# ── REGISTER BUYER ────────────────────────────────────
@router.post("/register-buyer")
async def register_buyer(data: BuyerCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.phone == data.phone))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User already exists with this phone number")
    user = User(
        phone=data.phone,
        name=data.name,
        role="buyer",
        hashed_password=pwd_context.hash(data.password)
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"id": str(user.id), "message": "Buyer account created", "name": user.name}

# ── LOGIN ─────────────────────────────────────────────
@router.post("/login")
async def login(data: LoginSchema, db: AsyncSession = Depends(get_db)):
    # Normalize phone number - try both formats
    phone = data.phone.strip()
    phone_variants = [phone]

    if phone.startswith('0'):
        phone_variants.append('92' + phone[1:])
    elif phone.startswith('92'):
        phone_variants.append('0' + phone[2:])
    elif not phone.startswith('92'):
        phone_variants.append('92' + phone)

    user = None
    for p in phone_variants:
        result = await db.execute(select(User).where(User.phone == p))
        user = result.scalar_one_or_none()
        if user:
            break

    if not user or not user.hashed_password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not pwd_context.verify(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token(str(user.id), str(user.role.value if hasattr(user.role, 'value') else user.role))

    # Auto-fix phone format in stores
    try:
        from app.models.models import Store
        phone_variants = [
            user.phone,
            '92' + user.phone.lstrip('0') if user.phone.startswith('0') else user.phone,
            '0' + user.phone[2:] if user.phone.startswith('92') else user.phone
        ]
        for phone in phone_variants:
            store_result = await db.execute(
                select(Store).where(Store.whatsapp_number == phone)
            )
            existing_store = store_result.scalar_one_or_none()
            if existing_store and existing_store.owner_id != user.id:
                existing_store.owner_id = user.id
                await db.commit()
                break
    except:
        pass

    return {
        "access_token": token,
        "token_type":   "bearer",
        "name":         user.name,
        "role":         user.role.value if hasattr(user.role, 'value') else user.role
    }

# ── SET / RESET PASSWORD ──────────────────────────────
@router.post("/set-password")
async def set_password(data: SetPassword, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.phone == data.phone))
    user   = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.hashed_password = pwd_context.hash(data.new_password)
    await db.commit()
    return {"message": f"Password updated for {user.name}"}

# ── GET CURRENT USER (token required) ─────────────────
@router.get("/me")
async def get_me(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Login required")
    payload = verify_token(authorization.split(" ")[1])
    result  = await db.execute(select(User).where(User.id == payload["sub"]))
    user    = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id":   str(user.id),
        "name": user.name,
        "role": user.role.value if hasattr(user.role, 'value') else user.role,
        "phone": user.phone
    }

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.models import Listing, Store
from app.routes.auth import get_current_local_user
from app.services.supabase_storage import upload_public_image
from pydantic import BaseModel
from typing import Optional
import uuid

router = APIRouter()

class ListingCreate(BaseModel):
    store_id: str
    title: str
    description: Optional[str] = None
    price: float
    currency: Optional[str] = "PKR"
    image_url: Optional[str] = None
    delivery_available: Optional[bool] = False

class ListingUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    image_url: Optional[str] = None
    is_available: Optional[bool] = None
    delivery_available: Optional[bool] = None


async def get_owned_store(db: AsyncSession, user_id, store_id: str) -> Store:
    result = await db.execute(
        select(Store).where(
            Store.id == uuid.UUID(store_id),
            Store.owner_id == user_id,
            Store.is_active == True,
        )
    )
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=403, detail="You do not own this store")
    return store


async def get_owned_listing(db: AsyncSession, user_id, listing_id: str) -> Listing:
    result = await db.execute(select(Listing).where(Listing.id == uuid.UUID(listing_id)))
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    await get_owned_store(db, user_id, str(listing.store_id))
    return listing


@router.post("/upload-image")
async def upload_listing_image(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    await get_current_local_user(authorization, db)

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image uploads are supported")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Image file is empty")
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be 5MB or smaller")

    image_url = await upload_public_image(content, file.content_type)
    return {"image_url": image_url}


@router.post("/")
async def create_listing(
    data: ListingCreate,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_local_user(authorization, db)
    await get_owned_store(db, user.id, data.store_id)

    listing = Listing(
        store_id=uuid.UUID(data.store_id),
        title=data.title,
        description=data.description,
        price=data.price,
        currency=data.currency,
        image_url=data.image_url,
        delivery_available=data.delivery_available,
        is_available=True
    )
    db.add(listing)
    await db.commit()
    await db.refresh(listing)

    return {"message": "Listing created", "listing_id": str(listing.id)}


@router.get("/store/{store_id}")
async def get_store_listings(store_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Listing).where(
            Listing.store_id == uuid.UUID(store_id),
            Listing.is_available == True
        )
    )
    return result.scalars().all()


@router.get("/{listing_id}")
async def get_listing(listing_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Listing).where(Listing.id == uuid.UUID(listing_id))
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing


@router.put("/{listing_id}")
async def update_listing(
    listing_id: str,
    data: ListingUpdate,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
):
    user = await get_current_local_user(authorization, db)
    listing = await get_owned_listing(db, user.id, listing_id)

    if data.title is not None:
        listing.title = data.title
    if data.description is not None:
        listing.description = data.description
    if data.price is not None:
        listing.price = data.price
    if data.image_url is not None:
        listing.image_url = data.image_url
    if data.is_available is not None:
        listing.is_available = data.is_available
    if data.delivery_available is not None:
        listing.delivery_available = data.delivery_available

    await db.commit()

    return {"message": "Listing updated"}


@router.delete("/{listing_id}")
async def delete_listing(
    listing_id: str,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_local_user(authorization, db)
    listing = await get_owned_listing(db, user.id, listing_id)

    listing.is_available = False
    await db.commit()

    return {"message": "Listing removed"}
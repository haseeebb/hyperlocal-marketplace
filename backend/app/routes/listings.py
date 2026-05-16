from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.models import Listing, Store
from pydantic import BaseModel
from typing import Optional
import uuid

router = APIRouter()

class ListingCreate(BaseModel):
    store_id: str
    title: str
    description: Optional[str] = None
    price: float
    currency: Optional[str] = "USD"
    image_url: Optional[str] = None
    delivery_available: Optional[bool] = False

class ListingUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    image_url: Optional[str] = None
    is_available: Optional[bool] = None
    delivery_available: Optional[bool] = None


@router.post("/")
async def create_listing(data: ListingCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Store).where(Store.id == uuid.UUID(data.store_id))
    )
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")

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
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Listing).where(Listing.id == uuid.UUID(listing_id))
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

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
async def delete_listing(listing_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Listing).where(Listing.id == uuid.UUID(listing_id))
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    listing.is_available = False
    await db.commit()

    return {"message": "Listing removed"}
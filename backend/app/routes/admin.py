from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.models import Store, Listing, User
from app.routes.auth import get_current_local_user
from typing import Optional
import uuid
from datetime import datetime, timedelta

router = APIRouter()

async def get_admin(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_local_user(authorization, db)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.get("/stores/pending")
async def get_pending_stores(db: AsyncSession = Depends(get_db), admin=Depends(get_admin)):
    result = await db.execute(
        select(Store).where(Store.is_verified == False, Store.is_active == True)
    )
    stores = result.scalars().all()
    return {
        "count": len(stores),
        "stores": [
            {
                "id": str(s.id),
                "name": s.name,
                "category": s.category,
                "city": s.city,
                "whatsapp_number": s.whatsapp_number,
                "lat": float(s.lat) if s.lat else None,
                "lng": float(s.lng) if s.lng else None,
                "created_at": str(s.created_at)
            }
            for s in stores
        ]
    }


@router.get("/stores/all")
async def get_all_stores(db: AsyncSession = Depends(get_db), admin=Depends(get_admin)):
    result = await db.execute(select(Store).where(Store.is_active == True))
    stores = result.scalars().all()
    return {
        "count": len(stores),
        "stores": [
            {
                "id": str(s.id),
                "name": s.name,
                "category": s.category,
                "city": s.city,
                "whatsapp_number": s.whatsapp_number,
                "is_verified": s.is_verified,
                "lat": float(s.lat) if s.lat else None,
                "lng": float(s.lng) if s.lng else None,
                "created_at": str(s.created_at)
            }
            for s in stores
        ]
    }


@router.put("/stores/{store_id}/approve")
async def approve_store(store_id: str, db: AsyncSession = Depends(get_db), admin=Depends(get_admin)):
    result = await db.execute(select(Store).where(Store.id == uuid.UUID(store_id)))
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    store.is_verified = True
    await db.commit()
    return {"message": f"Store '{store.name}' approved"}


@router.put("/stores/{store_id}/reject")
async def reject_store(store_id: str, db: AsyncSession = Depends(get_db), admin=Depends(get_admin)):
    result = await db.execute(select(Store).where(Store.id == uuid.UUID(store_id)))
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    store.is_active = False
    await db.commit()
    return {"message": f"Store '{store.name}' rejected"}


@router.get("/listings/all")
async def get_all_listings(db: AsyncSession = Depends(get_db), admin=Depends(get_admin)):
    result = await db.execute(
        select(Listing, Store)
        .join(Store, Listing.store_id == Store.id)
        .where(Listing.is_available == True)
    )
    rows = result.all()
    return {
        "count": len(rows),
        "listings": [
            {
                "id": str(listing.id),
                "title": listing.title,
                "price": float(listing.price or 0),
                "store_name": store.name,
                "whatsapp_number": store.whatsapp_number,
                "city": store.city,
                "created_at": str(listing.created_at)
            }
            for listing, store in rows
        ]
    }


@router.delete("/listings/{listing_id}")
async def remove_bad_listing(listing_id: str, db: AsyncSession = Depends(get_db), admin=Depends(get_admin)):
    result = await db.execute(select(Listing).where(Listing.id == uuid.UUID(listing_id)))
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    listing.is_available = False
    await db.commit()
    return {"message": "Listing removed"}


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db), admin=Depends(get_admin)):
    one_week_ago = datetime.utcnow() - timedelta(days=7)
    total_stores       = await db.execute(select(func.count()).select_from(Store).where(Store.is_active == True))
    verified_stores    = await db.execute(select(func.count()).select_from(Store).where(Store.is_verified == True, Store.is_active == True))
    pending_stores     = await db.execute(select(func.count()).select_from(Store).where(Store.is_verified == False, Store.is_active == True))
    total_listings     = await db.execute(select(func.count()).select_from(Listing).where(Listing.is_available == True))
    new_stores_week    = await db.execute(select(func.count()).select_from(Store).where(Store.created_at >= one_week_ago, Store.is_active == True))
    return {
        "total_stores":         total_stores.scalar(),
        "verified_stores":      verified_stores.scalar(),
        "pending_stores":       pending_stores.scalar(),
        "total_listings":       total_listings.scalar(),
        "new_stores_this_week": new_stores_week.scalar()
    }

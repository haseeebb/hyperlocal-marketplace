from fastapi import APIRouter, Query, Depends
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func
from app.database import get_db
from app.models.models import Listing, Store, Review
import uuid

router = APIRouter()

@router.get("/")
async def search_listings(
    q: str = Query("", description="Search query"),
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    city: Optional[str] = None,
    page: int = 1,
    db: AsyncSession = Depends(get_db)
):
    # PostgreSQL search
    query = (
        select(
            Listing, Store,
            func.coalesce(func.avg(Review.rating), 0).label('avg_rating'),
            func.count(Review.id).label('review_count')
        )
        .join(Store, Listing.store_id == Store.id)
        .outerjoin(Review, Review.listing_id == Listing.id)
        .where(
            Listing.is_available == True,
            Store.is_verified == True,
            Store.is_active == True
        )
        .group_by(Listing.id, Store.id)
    )
    if q:
        query = query.where(
            or_(
                Listing.title.ilike(f"%{q}%"),
                Listing.description.ilike(f"%{q}%"),
                Store.name.ilike(f"%{q}%")
            )
        )
    if category:
        query = query.where(Store.category == category)
    if min_price is not None:
        query = query.where(Listing.price >= min_price)
    if max_price is not None:
        query = query.where(Listing.price <= max_price)
    if city:
        query = query.where(Store.city.ilike(f"%{city}%"))

    result = await db.execute(query.limit(20).offset((page - 1) * 20))
    rows = result.all()

    hits = [{
        "id":                 str(listing.id),
        "title":              listing.title,
        "description":        listing.description or "",
        "price":              float(listing.price or 0),
        "currency":           listing.currency or "PKR",
        "image_url":          listing.image_url or "",
        "store_name":         store.name,
        "store_id":           str(store.id),
        "whatsapp_number":    store.whatsapp_number,
        "city":               store.city or "",
        "category":           store.category if store.category else "",
        "delivery_available": listing.delivery_available,
        "lat":                float(store.lat) if store.lat else None,
        "lng":                float(store.lng) if store.lng else None,
        "created_at":         str(listing.created_at),
        "avg_rating":         round(float(avg_rating), 1),
        "review_count":       review_count,
    } for listing, store, avg_rating, review_count in rows]

    # Fetch top-2 reviews per listing
    for hit in hits:
        reviews_result = await db.execute(
            select(Review)
            .where(Review.listing_id == uuid.UUID(hit["id"]))
            .order_by(Review.created_at.desc())
            .limit(2)
        )
        reviews = reviews_result.scalars().all()
        hit["reviews"] = [
            {
                "buyer_name": r.buyer_name,
                "rating":     r.rating,
                "comment":    r.comment or ""
            }
            for r in reviews
        ]

    return {"hits": hits, "query": q, "estimatedTotalHits": len(hits)}

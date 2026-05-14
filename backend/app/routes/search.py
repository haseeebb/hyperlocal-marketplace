from fastapi import APIRouter, Query, Depends
from typing import Optional
import meilisearch, os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from app.database import get_db
from app.models.models import Listing, Store

router = APIRouter()

try:
    client = meilisearch.Client(
        os.getenv("MEILI_URL", "http://localhost:7700"),
        os.getenv("MEILI_KEY", "masterkey123")
    )
    MEILI_AVAILABLE = True
except Exception:
    MEILI_AVAILABLE = False

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
    # Try Meilisearch first
    try:
        filters = []
        if category:
            filters.append(f'category = "{category}"')
        if min_price is not None:
            filters.append(f"price >= {min_price}")
        if max_price is not None:
            filters.append(f"price <= {max_price}")
        if city:
            filters.append(f'city = "{city}"')

        results = client.index("listings").search(q, {
            "filter": " AND ".join(filters) if filters else None,
            "limit": 20,
            "offset": (page - 1) * 20
        })
        return results
    except Exception:
        pass

    # Fallback: PostgreSQL search
    query = select(Listing, Store).join(Store, Listing.store_id == Store.id).where(
        Listing.is_available == True,
        Store.is_verified == True,
        Store.is_active == True
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
        "whatsapp_number":    store.whatsapp_number,
        "city":               store.city or "",
        "category":           store.category.value if store.category else "",
        "delivery_available": listing.delivery_available,
        "lat":                float(store.lat) if store.lat else None,
        "lng":                float(store.lng) if store.lng else None,
        "created_at":         str(listing.created_at),
    } for listing, store in rows]

    return {"hits": hits, "query": q, "estimatedTotalHits": len(hits)}

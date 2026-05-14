from fastapi import APIRouter, Query
from typing import Optional
import meilisearch, os

router = APIRouter()

client = meilisearch.Client(
    os.getenv("MEILI_URL", "http://localhost:7700"),
    os.getenv("MEILI_KEY", "masterkey123")
)

@router.get("/")
async def search_listings(
    q: str = Query("", description="Search query"),
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    city: Optional[str] = None,
    page: int = 1
):
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
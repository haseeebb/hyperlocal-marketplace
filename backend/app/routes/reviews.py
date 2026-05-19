from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.models import Review
from pydantic import BaseModel
from typing import Optional
import uuid

router = APIRouter()

class ReviewCreate(BaseModel):
    store_id:   str
    listing_id: Optional[str] = None
    buyer_name: str
    rating:     int
    comment:    Optional[str] = None

@router.post("/")
async def create_review(data: ReviewCreate, db: AsyncSession = Depends(get_db)):
    if data.rating < 1 or data.rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")

    review = Review(
        store_id=uuid.UUID(data.store_id),
        listing_id=uuid.UUID(data.listing_id) if data.listing_id else None,
        buyer_name=data.buyer_name,
        rating=data.rating,
        comment=data.comment
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return {"message": "Review submitted successfully", "id": str(review.id)}

@router.get("/store/{store_id}")
async def get_store_reviews(store_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Review)
        .where(Review.store_id == uuid.UUID(store_id))
        .order_by(Review.created_at.desc())
    )
    reviews = result.scalars().all()

    avg_result = await db.execute(
        select(func.avg(Review.rating))
        .where(Review.store_id == uuid.UUID(store_id))
    )
    avg_rating = avg_result.scalar() or 0

    return {
        "reviews": [
            {
                "id":         str(r.id),
                "buyer_name": r.buyer_name,
                "rating":     r.rating,
                "comment":    r.comment,
                "created_at": str(r.created_at)
            }
            for r in reviews
        ],
        "average_rating": round(float(avg_rating), 1),
        "total_reviews":  len(reviews)
    }

@router.get("/listing/{listing_id}")
async def get_listing_reviews(listing_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Review)
        .where(Review.listing_id == uuid.UUID(listing_id))
        .order_by(Review.created_at.desc())
    )
    reviews = result.scalars().all()
    return [
        {
            "id":         str(r.id),
            "buyer_name": r.buyer_name,
            "rating":     r.rating,
            "comment":    r.comment,
            "created_at": str(r.created_at)
        }
        for r in reviews
    ]

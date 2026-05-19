from sqlalchemy import Column, String, Boolean, Numeric, Text, DateTime, ForeignKey, Enum, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, declarative_base
import uuid, datetime, enum

Base = declarative_base()

class UserRole(str, enum.Enum):
    buyer = "buyer"
    seller = "seller"
    admin = "admin"

class StoreCategory(str, enum.Enum):
    products = "products"
    services = "services"
    restaurant = "restaurant"
    hotel = "hotel"

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone = Column(String(20), unique=True, nullable=False)
    name = Column(String(100))
    role = Column(Enum(UserRole), default=UserRole.buyer)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    store = relationship("Store", back_populates="owner", uselist=False)
    hashed_password = Column(String(255), nullable=True)

class Store(Base):
    __tablename__ = "stores"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    name = Column(String(150), nullable=False)
    description = Column(Text)
    category = Column(Enum(StoreCategory))
    city = Column(String(100))
    lat = Column(Numeric(9, 6))
    lng = Column(Numeric(9, 6))
    whatsapp_number = Column(String(20))
    is_verified = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    owner = relationship("User", back_populates="store")
    listings = relationship("Listing", back_populates="store")

class Listing(Base):
    __tablename__ = "listings"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(UUID(as_uuid=True), ForeignKey("stores.id"))
    title = Column(String(200), nullable=False)
    description = Column(Text)
    price = Column(Numeric(10, 2))
    currency = Column(String(10), default="USD")
    image_url = Column(Text)
    is_available = Column(Boolean, default=True)
    delivery_available = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    store = relationship("Store", back_populates="listings")

class Review(Base):
    __tablename__ = "reviews"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    listing_id = Column(UUID(as_uuid=True), ForeignKey("listings.id"), nullable=True)
    store_id   = Column(UUID(as_uuid=True), ForeignKey("stores.id"), nullable=False)
    buyer_name = Column(String(100), nullable=False)
    rating     = Column(Integer, nullable=False)
    comment    = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
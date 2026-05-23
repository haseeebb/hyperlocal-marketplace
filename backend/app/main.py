from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import stores, listings, search, admin, auth, whatsapp, reviews

app = FastAPI(
    title="Hyperlocal Marketplace API",
    version="1.0.0",
    swagger_ui_parameters={"persistAuthorization": True},
    openapi_tags=[
        {"name": "auth"},
        {"name": "stores"},
        {"name": "listings"},
        {"name": "search"},
        {"name": "admin"},
        {"name": "whatsapp"},
    ]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    allow_credentials=False,
)
app.include_router(auth.router,     prefix="/api/auth",     tags=["auth"])
app.include_router(stores.router,   prefix="/api/stores",   tags=["stores"])
app.include_router(listings.router, prefix="/api/listings", tags=["listings"])
app.include_router(search.router,   prefix="/api/search",   tags=["search"])
app.include_router(admin.router,    prefix="/api/admin",    tags=["admin"])
app.include_router(whatsapp.router, prefix="/webhook",     tags=["whatsapp"])
app.include_router(reviews.router,  prefix="/api/reviews", tags=["reviews"])

@app.get("/")
async def health():
    return {"status": "running"}
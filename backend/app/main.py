from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
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
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
    allow_credentials=False,
    max_age=3600,
)

@app.options("/{rest_of_path:path}")
async def preflight_handler(rest_of_path: str):
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
            "Access-Control-Allow-Headers": "*",
        }
    )

app.include_router(auth.router,     prefix="/api/auth",     tags=["auth"])
app.include_router(stores.router,   prefix="/api/stores",   tags=["stores"])
app.include_router(listings.router, prefix="/api/listings", tags=["listings"])
app.include_router(search.router,   prefix="/api/search",   tags=["search"])
app.include_router(admin.router,    prefix="/api/admin",    tags=["admin"])
app.include_router(whatsapp.router, prefix="/webhook",      tags=["whatsapp"])
app.include_router(reviews.router,  prefix="/api/reviews",  tags=["reviews"])

@app.get("/")
async def health():
    return {"status": "running"}
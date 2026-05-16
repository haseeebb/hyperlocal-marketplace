from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from fastapi.openapi.utils import get_openapi
from app.routes import stores, listings, search, admin, auth, whatsapp
security = HTTPBearer()

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

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="Hyperlocal Marketplace API",
        version="1.0.0",
        routes=app.routes,
    )
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
    }
    openapi_schema["security"] = [{"BearerAuth": []}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router,     prefix="/api/auth",     tags=["auth"])
app.include_router(stores.router,   prefix="/api/stores",   tags=["stores"])
app.include_router(listings.router, prefix="/api/listings", tags=["listings"])
app.include_router(search.router,   prefix="/api/search",   tags=["search"])
app.include_router(admin.router,    prefix="/api/admin",    tags=["admin"])
app.include_router(whatsapp.router, prefix="/webhook", tags=["whatsapp"])

@app.get("/")
async def health():
    return {"status": "running"}
import meilisearch
import os

client = meilisearch.Client(
    os.getenv("MEILI_URL", "http://localhost:7700"),
    os.getenv("MEILI_KEY", "masterkey123")
)

INDEX_NAME = "listings"

def get_index():
    return client.index(INDEX_NAME)

def setup_index():
    try:
        client.create_index(INDEX_NAME, {"primaryKey": "id"})
    except Exception:
        pass

    get_index().update_filterable_attributes([
        "category", "city", "price", "is_available", "delivery_available"
    ])
    get_index().update_sortable_attributes([
        "price", "created_at"
    ])
    get_index().update_searchable_attributes([
        "title", "description", "store_name", "city"
    ])
    print("✅ Meilisearch setup completed")


def index_listing(listing, store):
    document = {
        "id":                 str(listing.id),
        "title":              listing.title,
        "description":        listing.description or "",
        "price":              float(listing.price or 0),
        "currency":           listing.currency or "USD",
        "image_url":          listing.image_url or "",
        "is_available":       listing.is_available,
        "delivery_available": listing.delivery_available,
        "store_id":           str(listing.store_id),
        "store_name":         store.name,
        "whatsapp_number":    store.whatsapp_number,
        "city":               store.city or "",
        "category":           store.category.value if store.category else "",
        "lat":                float(store.lat) if store.lat else None,
        "lng":                float(store.lng) if store.lng else None,
        "created_at":         str(listing.created_at),
    }
    get_index().add_documents([document])


def remove_listing(listing_id: str):
    get_index().delete_document(listing_id)


def reindex_all(listings_with_stores: list):
    documents = []
    for listing, store in listings_with_stores:
        documents.append({
            "id":                 str(listing.id),
            "title":              listing.title,
            "description":        listing.description or "",
            "price":              float(listing.price or 0),
            "currency":           listing.currency or "USD",
            "image_url":          listing.image_url or "",
            "is_available":       listing.is_available,
            "delivery_available": listing.delivery_available,
            "store_id":           str(listing.store_id),
            "store_name":         store.name,
            "whatsapp_number":    store.whatsapp_number,
            "city":               store.city or "",
            "category":           store.category.value if store.category else "",
            "lat":                float(store.lat) if store.lat else None,
            "lng":                float(store.lng) if store.lng else None,
            "created_at":         str(listing.created_at),
        })
    if documents:
        get_index().add_documents(documents)
    return len(documents)
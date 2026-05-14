import httpx
import os
import cloudinary
import cloudinary.uploader
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionLocal
from app.models.models import Store, Listing, User
from app.services.meili_service import index_listing, remove_listing
from sqlalchemy import select

# --- Config ---
WHATSAPP_TOKEN  = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_ID")
# In-memory session storage (replaces Redis)
sessions = {}

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

# ── WhatsApp helpers ──────────────────────────────────
async def send_message(to: str, text: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages",
            headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"},
            json={
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": text}
            }
        )
        print(f"WhatsApp send: {response.status_code}")

# ── Session helpers ───────────────────────────────────
async def get_session(phone: str) -> dict:
    return sessions.get(phone, {"step": "idle"})

async def save_session(phone: str, session: dict):
    sessions[phone] = session

async def clear_session(phone: str):
    sessions.pop(phone, None)

# ── Image upload helper ───────────────────────────────
async def download_and_upload_image(media_id: str) -> str:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"https://graph.facebook.com/v19.0/{media_id}",
            headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
        )
        media_url = r.json().get("url")
        img_response = await client.get(
            media_url,
            headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
        )
        result = cloudinary.uploader.upload(img_response.content)
        return result["secure_url"]

# ── Helper: get active store for sender ───────────────
async def get_active_store(sender: str):
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Store).where(
                Store.whatsapp_number == sender,
                Store.is_active == True
            )
        )
        return result.scalar_one_or_none()

# ── Main message handler ──────────────────────────────
async def handle_message(sender: str, text: str, media_id: str = None):
    session = await get_session(sender)
    step    = session.get("step", "idle")

    print(f"Message from {sender}: text='{text}', media_id={media_id}, step={step}")

    # ══════════════════════════════════════
    # REGISTRATION FLOW
    # ══════════════════════════════════════
    if text in ["register", "hello", "hi", "start", "مرحبا"]:

        # ── Check if store already exists for this number ──
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Store).where(
                    Store.whatsapp_number == sender,
                    Store.is_active == True
                )
            )
            existing = result.scalar_one_or_none()

        if existing:
            await send_message(sender,
                f"Welcome back! 👋\n\n"
                f"Your store *{existing.name}* is already registered.\n\n"
                f"Reply *menu* to manage your store."
            )
            return

        await send_message(sender,
            "Welcome to Find X Marketplace! 🎉\n\n"
            "Let's set up your store in a few easy steps.\n\n"
            "Reply with a number to continue:\n\n"
            "1️⃣ — Register New Store\n"
            "2️⃣ — Check Store Status\n\n"
            "Or reply *1* to start registration now."
        )
        session = {"step": "reg_start"}
        await save_session(sender, session)
        return

    elif step == "reg_start":
        if text == "1":
            session = {"step": "reg_name"}
            await save_session(sender, session)
            await send_message(sender,
                "Great! Let's register your store. 🏪\n\n"
                "What is your full name?"
            )
        elif text == "2":
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Store).where(Store.whatsapp_number == sender)
                )
                store = result.scalar_one_or_none()
            if store:
                status = "✅ Verified and Active" if store.is_verified and store.is_active else "⏳ Pending Approval"
                await send_message(sender,
                    f"🏪 *{store.name}*\n\n"
                    f"Status: {status}\n"
                    f"City: {store.city or 'Not set'}\n\n"
                    "Reply *menu* to manage your store."
                )
            else:
                await send_message(sender,
                    "No store found for your number.\n\n"
                    "Reply *register* to create one."
                )
            await clear_session(sender)
        else:
            await send_message(sender,
                "Please reply with:\n"
                "1️⃣ — Register New Store\n"
                "2️⃣ — Check Store Status"
            )

    elif step == "reg_name":
        session["owner_name"] = text.title()
        session["step"]       = "reg_store_name"
        await save_session(sender, session)
        await send_message(sender,
            f"Nice to meet you, {session['owner_name']}! 👋\n\n"
            "What is your store name?"
        )

    elif step == "reg_store_name":
        session["store_name"] = text.title()
        session["step"]       = "reg_category"
        await save_session(sender, session)
        await send_message(sender,
            "What type of store is it? Reply with a number:\n\n"
            "1️⃣ Products\n"
            "2️⃣ Services\n"
            "3️⃣ Restaurant\n"
            "4️⃣ Hotel"
        )

    elif step == "reg_category":
        cats = {"1": "products", "2": "services", "3": "restaurant", "4": "hotel"}
        if text not in cats:
            await send_message(sender, "Please reply with 1, 2, 3, or 4.")
            return
        session["category"] = cats[text]
        session["step"]     = "reg_city"
        await save_session(sender, session)
        await send_message(sender, "Which area / city is your store located in?")

    elif step == "reg_city":
        session["city"] = text.title()
        await save_session(sender, session)

        async with AsyncSessionLocal() as db:

            # ── Double-check uniqueness before saving ──
            check = await db.execute(
                select(Store).where(
                    Store.whatsapp_number == sender,
                    Store.is_active == True
                )
            )
            if check.scalar_one_or_none():
                await clear_session(sender)
                await send_message(sender,
                    "❌ A store is already registered with this number.\n\n"
                    "Reply *menu* to manage your existing store."
                )
                return

            # Find or create user
            result = await db.execute(
                select(User).where(User.phone == sender)
            )
            user = result.scalar_one_or_none()

            if not user:
                user = User(
                    phone=sender,
                    name=session["owner_name"],
                    role="seller"
                )
                db.add(user)
                await db.flush()
            else:
                user.role = "seller"

            store = Store(
                owner_id=user.id,
                name=session["store_name"],
                category=session["category"],
                city=session["city"],
                whatsapp_number=sender,
                is_verified=False
            )
            db.add(store)
            await db.commit()

        await clear_session(sender)
        await send_message(sender,
            f"✅ Your store *{session['store_name']}* has been submitted!\n\n"
            "Our team will review and approve it within 24 hours.\n"
            "You'll receive a message here once approved.\n\n"
            "Once approved, reply *menu* to manage your store."
        )

    # ══════════════════════════════════════
    # MAIN MENU
    # ══════════════════════════════════════
    elif text == "menu":
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Store).where(
                    Store.whatsapp_number == sender,
                    Store.is_verified == True,
                    Store.is_active == True
                )
            )
            store = result.scalar_one_or_none()

        if not store:
            await send_message(sender,
                "⚠️ Your store is not verified yet.\n"
                "Please wait for admin approval.\n\n"
                "If you haven't registered yet, reply *register*."
            )
            return

        await send_message(sender,
            f"🏪 *{store.name}* — Store Menu\n\n"
            "Reply with a number:\n\n"
            "1️⃣ — Add Product\n"
            "2️⃣ — My Products\n"
            "3️⃣ — Update Price\n"
            "4️⃣ — Delete Product\n"
            "5️⃣ — Delivery ON\n"
            "6️⃣ — Delivery OFF\n"
            "7️⃣ — Pause Store\n"
            "8️⃣ — Resume Store\n\n"
            "Or type the command name directly."
        )

    # ══════════════════════════════════════
    # ADD PRODUCT FLOW
    # ══════════════════════════════════════
    elif text == "add product":
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Store).where(
                    Store.whatsapp_number == sender,
                    Store.is_verified == True,
                    Store.is_active == True
                )
            )
            store = result.scalar_one_or_none()

        if not store:
            await send_message(sender,
                "⚠️ Your store is not verified yet.\n"
                "Please wait for admin approval before adding products."
            )
            return

        session = {"step": "add_title"}
        await save_session(sender, session)
        await send_message(sender, "What is the product or service name?")

    elif step == "add_title":
        session["title"] = text.title()
        session["step"]  = "add_price"
        await save_session(sender, session)
        await send_message(sender,
            f"Got it: *{session['title']}* ✅\n\n"
            "What is the price? (numbers only, e.g. 500)"
        )

    elif step == "add_price":
        try:
            price = float(text.replace(",", "").replace("rs", "").replace("pkr", "").strip())
            session["price"] = price
        except:
            await send_message(sender, "Please send a number only. Example: 500 or 9.99")
            return
        session["step"] = "add_description"
        await save_session(sender, session)
        await send_message(sender,
            "Add a short description.\n"
            "(or reply *skip* to skip)"
        )

    elif step == "add_description":
        session["description"] = "" if text == "skip" else text
        session["step"]        = "add_image"
        await save_session(sender, session)
        await send_message(sender,
            "Now send a photo of the product 📸\n"
            "(or reply *skip* to skip)"
        )

    elif step == "add_image":
        image_url = None

        if media_id:
            try:
                image_url = await download_and_upload_image(media_id)
            except Exception as e:
                print(f"Image upload error: {e}")
                await send_message(sender, "Image upload failed. Saving without image.")
        elif text == "skip":
            pass
        else:
            await send_message(sender, "Please send a photo or reply *skip*.")
            return

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Store).where(
                    Store.whatsapp_number == sender,
                    Store.is_verified == True,
                    Store.is_active == True
                )
            )
            store = result.scalar_one_or_none()
            if not store:
                await send_message(sender, "Store not found or not verified.")
                await clear_session(sender)
                return

            listing = Listing(
                store_id=store.id,
                title=session["title"],
                description=session.get("description", ""),
                price=session["price"],
                image_url=image_url,
                is_available=True
            )
            db.add(listing)
            await db.commit()
            await db.refresh(listing)
            index_listing(listing, store)

        await clear_session(sender)
        await send_message(sender,
            f"✅ *{session['title']}* has been listed successfully!\n\n"
            "Reply *menu* to see more options."
        )

    # ══════════════════════════════════════
    # VIEW PRODUCTS
    # ══════════════════════════════════════
    elif text == "my products":
        async with AsyncSessionLocal() as db:
            store_result = await db.execute(
                select(Store).where(
                    Store.whatsapp_number == sender,
                    Store.is_active == True
                )
            )
            store = store_result.scalar_one_or_none()
            if not store:
                await send_message(sender, "No store found. Reply *register* to create one.")
                return

            listings_result = await db.execute(
                select(Listing).where(
                    Listing.store_id == store.id,
                    Listing.is_available == True
                )
            )
            items = listings_result.scalars().all()

        if not items:
            await send_message(sender,
                "You have no active listings.\n"
                "Reply *add product* to add one."
            )
            return

        msg = f"📦 *Your listings ({len(items)}):*\n\n"
        for i, item in enumerate(items, 1):
            msg += f"{i}. {item.title} — {item.price} {item.currency}\n"
        msg += "\nReply *menu* for more options."
        await send_message(sender, msg)

    # ══════════════════════════════════════
    # DELETE PRODUCT
    # ══════════════════════════════════════
    elif text == "delete product":
        async with AsyncSessionLocal() as db:
            store_result = await db.execute(
                select(Store).where(
                    Store.whatsapp_number == sender,
                    Store.is_active == True
                )
            )
            store = store_result.scalar_one_or_none()
            if not store:
                await send_message(sender, "No store found.")
                return

            listings_result = await db.execute(
                select(Listing).where(
                    Listing.store_id == store.id,
                    Listing.is_available == True
                )
            )
            items = listings_result.scalars().all()

        if not items:
            await send_message(sender, "You have no listings to delete.")
            return

        msg = "Which product do you want to delete?\nReply with the number:\n\n"
        for i, item in enumerate(items, 1):
            msg += f"{i}. {item.title}\n"

        session = {
            "step":  "confirm_delete",
            "items": [{"id": str(item.id), "title": item.title} for item in items]
        }
        await save_session(sender, session)
        await send_message(sender, msg)

    elif step == "confirm_delete":
        items = session.get("items", [])
        try:
            index = int(text) - 1
            if index < 0 or index >= len(items):
                raise ValueError
        except:
            await send_message(sender, f"Please reply with a number between 1 and {len(items)}.")
            return

        selected = items[index]
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Listing).where(Listing.id == selected["id"])
            )
            listing = result.scalar_one_or_none()
            if listing:
                listing.is_available = False
                await db.commit()
                remove_listing(selected["id"])

        await clear_session(sender)
        await send_message(sender,
            f"✅ *{selected['title']}* has been deleted.\n\n"
            "Reply *menu* for more options."
        )

    # ══════════════════════════════════════
    # UPDATE PRICE
    # ══════════════════════════════════════
    elif text == "update price":
        async with AsyncSessionLocal() as db:
            store_result = await db.execute(
                select(Store).where(
                    Store.whatsapp_number == sender,
                    Store.is_active == True
                )
            )
            store = store_result.scalar_one_or_none()
            if not store:
                await send_message(sender, "No store found.")
                return

            listings_result = await db.execute(
                select(Listing).where(
                    Listing.store_id == store.id,
                    Listing.is_available == True
                )
            )
            items = listings_result.scalars().all()

        if not items:
            await send_message(sender, "You have no listings.")
            return

        msg = "Which product price do you want to update?\nReply with the number:\n\n"
        for i, item in enumerate(items, 1):
            msg += f"{i}. {item.title} — {item.price}\n"

        session = {
            "step":  "select_product_price",
            "items": [{"id": str(item.id), "title": item.title} for item in items]
        }
        await save_session(sender, session)
        await send_message(sender, msg)

    elif step == "select_product_price":
        items = session.get("items", [])
        try:
            index = int(text) - 1
            if index < 0 or index >= len(items):
                raise ValueError
        except:
            await send_message(sender, f"Please reply with a number between 1 and {len(items)}.")
            return

        session["selected_item"] = items[index]
        session["step"]          = "enter_new_price"
        await save_session(sender, session)
        await send_message(sender,
            f"What is the new price for *{items[index]['title']}*?"
        )

    elif step == "enter_new_price":
        try:
            new_price = float(text.replace(",", "").replace("rs", "").replace("pkr", "").strip())
        except:
            await send_message(sender, "Please send a number only. Example: 750")
            return

        selected = session.get("selected_item")
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Listing).where(Listing.id == selected["id"])
            )
            listing = result.scalar_one_or_none()
            if listing:
                listing.price = new_price
                await db.commit()
                store_result = await db.execute(
                    select(Store).where(Store.id == listing.store_id)
                )
                store = store_result.scalar_one_or_none()
                if store:
                    index_listing(listing, store)

        await clear_session(sender)
        await send_message(sender,
            f"✅ Price updated to *{new_price}* for *{selected['title']}*.\n\n"
            "Reply *menu* for more options."
        )

    # ══════════════════════════════════════
    # DELIVERY TOGGLE
    # ══════════════════════════════════════
    elif text in ["delivery on", "delivery off"]:
        status = text == "delivery on"
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Store).where(
                    Store.whatsapp_number == sender,
                    Store.is_active == True
                )
            )
            store = result.scalar_one_or_none()
            if store:
                store.delivery_available = status
                await db.commit()
        await send_message(sender,
            f"✅ Delivery has been turned *{'on' if status else 'off'}*."
        )

    # ══════════════════════════════════════
    # PAUSE / RESUME STORE
    # ══════════════════════════════════════
    elif text in ["pause store", "resume store"]:
        status = text == "resume store"
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Store).where(
                    Store.whatsapp_number == sender,
                    Store.is_active == True
                )
            )
            store = result.scalar_one_or_none()
            if store:
                store.is_active = status
                await db.commit()
        await send_message(sender,
            f"✅ Your store is now *{'visible' if status else 'hidden'}*."
        )

    # ══════════════════════════════════════
    # NUMBER SHORTCUTS FROM MENU
    # ══════════════════════════════════════
    elif text.strip() in ["1","2","3","4","5","6","7","8"]:
        shortcuts = {
            "1": "add product",
            "2": "my products",
            "3": "update price",
            "4": "delete product",
            "5": "delivery on",
            "6": "delivery off",
            "7": "pause store",
            "8": "resume store"
        }
        # Re-handle as the actual command
        await handle_message(sender, shortcuts[text.strip()], media_id)

    # ══════════════════════════════════════
    # UNKNOWN COMMAND
    # ══════════════════════════════════════
    else:
        await send_message(sender,
            "I didn't understand that. 🤔\n\n"
            "Reply *menu* to see all commands.\n"
            "Reply *register* to create a new store."
        )
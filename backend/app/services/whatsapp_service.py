import httpx
import os
import cloudinary
import cloudinary.uploader
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionLocal
from app.models.models import Store, Listing, User
from sqlalchemy import select

# --- Config ---
WHATSAPP_TOKEN  = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_ID")
# In-memory session storage (replaces Redis)
sessions = {}

def reset_session(phone: str):
    sessions[phone] = {"step": "idle"}

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
    sessions[phone] = {"step": "idle"}

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

    # GLOBAL M — resets everything
    if text.strip().lower() in ["m", "menu"] and step not in ["idle"]:
        sessions[sender] = {"step": "idle"}
        step = "idle"
        session = {"step": "idle"}

    # ══════════════════════════════════════
    # REGISTRATION FLOW
    # ══════════════════════════════════════
    if text in ["register", "hello", "hi", "start", "مرحبا", "r"]:

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
                f"Wapas khush amdeed! 👋\n\n"
                f"Aap ka store *{existing.name}* pehle se registered hai.\n\n"
                f"Store manage karne ke liye *M* likhein."
            )
            return

        await send_message(sender,
            "Find X Marketplace mein khush amdeed! 🎉\n\n"
            "Apna store register karein ya status check karein:\n\n"
            "1️⃣ — Naya Store Register Karen\n"
            "2️⃣ — Store Status Check Karen\n\n"
            "1 likhein registration shuru karne ke liye!"
        )
        session = {"step": "reg_start"}
        await save_session(sender, session)
        return

    elif step == "reg_start":
        if text == "1":
            session = {"step": "reg_name"}
            await save_session(sender, session)
            await send_message(sender,
                "Zabardast! Store register karte hain! 🏪\n\n"
                "Aap ka poora naam kya hai?"
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
                    f"Area: {store.city or 'Set nahi'}\n\n"
                    "Store manage karne ke liye *M* likhein."
                )
            else:
                await send_message(sender,
                    "Aap ke number pe koi store nahi mila.\n\n"
                    "Store banane ke liye *hi* likhein."
                )
            await clear_session(sender)
        else:
            await send_message(sender,
                "Kripya reply karein:\n"
                "1️⃣ — Naya Store Register Karen\n"
                "2️⃣ — Store Status Check Karen"
            )

    elif step == "reg_name":
        session["owner_name"] = text.title()
        session["step"]       = "reg_store_name"
        await save_session(sender, session)
        await send_message(sender,
            f"Khushi hui milke, {session['owner_name']}! 👋\n\n"
            "Aap ke store ka naam kya hai?"
        )

    elif step == "reg_store_name":
        session["store_name"] = text.title()
        session["step"]       = "reg_category"
        await save_session(sender, session)
        await send_message(sender,
            "Aap ka store kis qisam ka hai? Number reply karein:\n\n"
            "1️⃣ Products\n"
            "2️⃣ Services\n"
            "3️⃣ Restaurant\n"
            "4️⃣ Hotel"
        )

    elif step == "reg_category":
        cats = {"1": "products", "2": "services", "3": "restaurant", "4": "hotel"}
        if text not in cats:
            await send_message(sender, "Kripya 1, 2, 3, ya 4 likhein.")
            return
        session["category"] = cats[text]
        session["step"]     = "reg_city"
        await save_session(sender, session)
        await send_message(sender,
            "Aap ka store Lahore ke kis area mein hai?\n\n"
            "Misaal ke taur par:\n"
            "• Gulberg\n"
            "• DHA\n"
            "• Johar Town\n"
            "• Model Town\n"
            "• Bahria Town\n"
            "• Saddar\n\n"
            "Apna area naam likhein:"
        )

    elif step == "reg_city":
        session["city"] = text.title()
        session["step"] = "reg_password"
        await save_session(sender, session)
        await send_message(sender,
            "Bas thoda aur! 🎉\n\n"
            "Website login ke liye password set karein:\n"
            "(kam az kam 6 characters)"
        )

    elif step == "reg_password":
        if len(text.strip()) < 6:
            await send_message(sender, "Password kam az kam 6 characters ka hona chahiye. Dobara likhein.")
            return
        session["password"] = text.strip()
        session["step"] = "reg_confirm"
        await save_session(sender, session)
        await send_message(sender,
            "Password confirm karne ke liye dobara likhein:"
        )

    elif step == "reg_confirm":
        if text.strip() != session.get("password"):
            await send_message(sender,
                "❌ Password match nahi hua. Dobara enter karein:"
            )
            session["step"] = "reg_password"
            await save_session(sender, session)
            return

        # Now save everything including password
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
                    "❌ Is number pe pehle se ek store registered hai.\n\n"
                    "Apna store manage karne ke liye *M* likhein."
                )
                return

            # Find or create user
            result = await db.execute(
                select(User).where(User.phone == sender)
            )
            user = result.scalar_one_or_none()

            from passlib.context import CryptContext
            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

            if not user:
                user = User(
                    phone=sender,
                    name=session["owner_name"],
                    role="seller",
                    hashed_password=pwd_context.hash(session["password"])
                )
                db.add(user)
                await db.flush()
            else:
                user.role = "seller"
                user.hashed_password = pwd_context.hash(session["password"])

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
            f"✅ Aap ka store *{session['store_name']}* submit ho gaya!\n\n"
            "Hamari team 24 ghante mein review karegi.\n\n"
            f"Website login details:\n"
            f"📱 Phone: {sender}\n"
            f"🔑 Password: {session['password']}\n"
            f"🌐 Login: https://hyperlocal-marketplace-zeta.vercel.app/login.html\n\n"
            "Approve hone ke baad *M* likhein store manage karne ke liye."
        )

    # ══════════════════════════════════════
    # MAIN MENU
    # ══════════════════════════════════════
    elif text in ["menu", "m"]:
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
                "⚠️ Aap ka store abhi verify nahi hua.\n"
                "Admin approval ka intezaar karein.\n\n"
                "Agar registered nahi hain toh *hi* likhein."
            )
            return

        await send_message(sender,
            f"🏪 *{store.name}* — Store Menu\n\n"
            "Reply with a number:\n\n"
            "1️⃣ — Add Product\n"
            "2️⃣ — My Products\n"
            "3️⃣ — Update Price\n"
            "4️⃣ — Delete Product\n\n"
            "Or type the command name directly."
        )

    # ══════════════════════════════════════
    # NUMBER SHORTCUTS FROM MENU
    # ══════════════════════════════════════
    elif text.strip() in ["1","2","3","4"] and step not in [
        "reg_start", "reg_name", "reg_store_name", "reg_category", "reg_city",
        "reg_password", "reg_confirm",
        "add_title", "add_price", "add_description", "add_image",
        "confirm_delete", "select_product_price", "enter_new_price"
    ]:
        shortcuts = {
            "1": "add product",
            "2": "my products",
            "3": "update price",
            "4": "delete product",
        }
        await handle_message(sender, shortcuts[text.strip()], media_id)

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
                "⚠️ Aap ka store abhi verify nahi hua.\n"
                "Products add karne se pehle admin approval ka intezaar karein."
            )
            return

        session = {"step": "add_title"}
        await save_session(sender, session)
        await send_message(sender, "Product ya service ka naam kya hai?\n\n_(Wapas jane ke liye M likhein)_")

    elif step == "add_title":
        session["title"] = text.title()
        session["step"]  = "add_price"
        await save_session(sender, session)
        await send_message(sender,
            f"Theek hai: *{session['title']}* ✅\n\n"
            "Price kya hai? (sirf number, misaal: 500)"
        )

    elif step == "add_price":
        try:
            price = float(text.replace(",", "").replace("rs", "").replace("pkr", "").strip())
            session["price"] = price
        except:
            await send_message(sender, "Sirf number likhein. Misaal: 500 ya 9.99")
            return
        session["step"] = "add_description"
        await save_session(sender, session)
        await send_message(sender,
            "Mukhtasar description likhein.\n"
            "(ya *skip* likhein chorne ke liye)"
        )

    elif step == "add_description":
        session["description"] = "" if text == "skip" else text
        session["step"]        = "add_image"
        await save_session(sender, session)
        await send_message(sender,
            "Product ki photo bhejein 📸\n"
            "(ya *skip* likhein chorne ke liye)"
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
            await send_message(sender, "Photo bhejein ya *skip* likhein.")
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
                currency="PKR",
                image_url=image_url,
                is_available=True
            )
            db.add(listing)
            await db.commit()
            await db.refresh(listing)

        await clear_session(sender)
        await send_message(sender,
            f"✅ *{session['title']}* successfully list ho gaya!\n\n"
            "Aur options ke liye *M* likhein."
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
                await send_message(sender, "Koi store nahi mila. Store banane ke liye *hi* likhein.")
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
                "Aap ka koi active listing nahi hai.\n"
                "Product add karne ke liye *1* likhein."
            )
            return

        msg = f"📦 *Aap ke products ({len(items)}):*\n\n"
        for i, item in enumerate(items, 1):
            msg += f"{i}. {item.title} — {item.price} {item.currency}\n"
        msg += "\nAur options ke liye *M* likhein."
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

        msg = "Kaunsa product delete karna chahte hain?\nNumber reply karein:\n\n"
        for i, item in enumerate(items, 1):
            msg += f"{i}. {item.title}\n"
        msg += "\nWapas jane ke liye *M* likhein."

        session = {
            "step":  "confirm_delete",
            "items": [{"id": str(item.id), "title": item.title} for item in items]
        }
        await save_session(sender, session)
        await send_message(sender, msg)

    elif step == "confirm_delete":
        if text.strip().lower() in ["m", "menu"]:
            await clear_session(sender)
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Store).where(
                        Store.whatsapp_number == sender,
                        Store.is_verified == True,
                        Store.is_active == True
                    )
                )
                store = result.scalar_one_or_none()
            if store:
                await send_message(sender,
                    f"🏪 *{store.name}* — Store Menu\n\n"
                    "Number reply karein:\n\n"
                    "1️⃣ — Product Add Karen\n"
                    "2️⃣ — Mere Products Dekhein\n"
                    "3️⃣ — Price Update Karen\n"
                    "4️⃣ — Product Delete Karen\n\n"
                    "Ya seedha command likhein."
                )
            return
        items = session.get("items", [])
        try:
            index = int(text) - 1
            if index < 0 or index >= len(items):
                raise ValueError
        except:
            await send_message(sender, f"1 aur {len(items)} ke darmiyan number likhein.\nWapas jane ke liye *M* likhein.")
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

        await clear_session(sender)
        await send_message(sender,
            f"✅ *{selected['title']}* delete ho gaya.\n\n"
            "Aur options ke liye *M* likhein."
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

        msg = "Kis product ka price update karna chahte hain?\nNumber reply karein:\n\n"
        for i, item in enumerate(items, 1):
            msg += f"{i}. {item.title} — {item.price}\n"
        msg += "\nWapas jane ke liye *M* likhein."

        session = {
            "step":  "select_product_price",
            "items": [{"id": str(item.id), "title": item.title} for item in items]
        }
        await save_session(sender, session)
        await send_message(sender, msg)

    elif step == "select_product_price":
        if text.strip().lower() in ["m", "menu"]:
            sessions[sender] = {"step": "idle"}
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Store).where(
                        Store.whatsapp_number == sender,
                        Store.is_verified == True,
                        Store.is_active == True
                    )
                )
                store = result.scalar_one_or_none()
            if store:
                await send_message(sender,
                    f"🏪 *{store.name}* — Store Menu\n\n"
                    "Number reply karein:\n\n"
                    "1️⃣ — Product Add Karen\n"
                    "2️⃣ — Mere Products Dekhein\n"
                    "3️⃣ — Price Update Karen\n"
                    "4️⃣ — Product Delete Karen\n\n"
                    "Ya seedha command likhein."
                )
            return
        items = session.get("items", [])
        try:
            index = int(text) - 1
            if index < 0 or index >= len(items):
                raise ValueError
        except:
            await send_message(sender, f"1 aur {len(items)} ke darmiyan number likhein.")
            return
        session["selected_item"] = items[index]
        session["step"]          = "enter_new_price"
        await save_session(sender, session)
        await send_message(sender,
            f"*{items[index]['title']}* ka naya price kya hai?"
        )

    elif step == "enter_new_price":
        if text.strip().lower() in ["m", "menu"]:
            sessions[sender] = {"step": "idle"}
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Store).where(
                        Store.whatsapp_number == sender,
                        Store.is_verified == True,
                        Store.is_active == True
                    )
                )
                store = result.scalar_one_or_none()
            if store:
                await send_message(sender,
                    f"🏪 *{store.name}* — Store Menu\n\n"
                    "Number reply karein:\n\n"
                    "1️⃣ — Product Add Karen\n"
                    "2️⃣ — Mere Products Dekhein\n"
                    "3️⃣ — Price Update Karen\n"
                    "4️⃣ — Product Delete Karen\n\n"
                    "Ya seedha command likhein."
                )
            return
        try:
            new_price = float(text.replace(",", "").replace("rs", "").replace("pkr", "").strip())
        except:
            await send_message(sender, "Sirf number likhein. Misaal: 750")
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
        await clear_session(sender)
        await send_message(sender,
            f"✅ *{selected['title']}* ka price *{new_price}* ho gaya.\n\n"
            "Aur options ke liye *M* likhein."
        )

    # ══════════════════════════════════════
    # CANCEL / RESET
    # ══════════════════════════════════════
    elif text in ["cancel", "stop", "reset", "exit"]:
        await clear_session(sender)
        await send_message(sender,
            "✅ Cancel ho gaya.\n\n"
            "Dobara shuru karne ke liye *hi* likhein.\n"
            "Store manage karne ke liye *M* likhein."
        )

    # ══════════════════════════════════════
    # UNKNOWN COMMAND
    # ══════════════════════════════════════
    else:
        await send_message(sender,
            "Samajh nahi aaya. 🤔\n\n"
            "Store menu ke liye *M* likhein.\n"
            "Naya store register karne ke liye *R* likhein."
        )
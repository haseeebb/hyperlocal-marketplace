import httpx
import os
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionLocal
from app.models.models import Store, Listing, User
from app.services.supabase_storage import upload_public_image
from sqlalchemy import select

# --- Config ---
WHATSAPP_TOKEN  = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_ID")

# In-memory session storage
sessions = {}

# ── Session helpers ───────────────────────────────────
async def get_session(phone: str) -> dict:
    return sessions.get(phone, {"step": "idle"})

async def save_session(phone: str, session: dict):
    sessions[phone] = session

async def clear_session(phone: str):
    sessions[phone] = {"step": "idle"}

# ══════════════════════════════════════════════════════
# SEND HELPERS
# ══════════════════════════════════════════════════════

async def send_message(to: str, text: str):
    """Send plain text message"""
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
        print(f"WhatsApp send text: {response.status_code}")


async def send_buttons(to: str, text: str, buttons: list):
    """
    Send interactive reply buttons (max 3)
    buttons = [{"id": "btn_id", "title": "Button Text"}, ...]
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages",
            headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"},
            json={
                "messaging_product": "whatsapp",
                "to": to,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": text},
                    "action": {
                        "buttons": [
                            {"type": "reply", "reply": {"id": b["id"], "title": b["title"]}}
                            for b in buttons
                        ]
                    }
                }
            }
        )
        print(f"WhatsApp send buttons: {response.status_code}")
        if response.status_code != 200:
            print(f"Button error: {response.text}")
            # Fallback to text
            fallback = text + "\n\n"
            for i, b in enumerate(buttons, 1):
                fallback += f"{i}. {b['title']}\n"
            await send_message(to, fallback)


async def send_list(to: str, text: str, button_text: str, sections: list):
    """
    Send interactive list message (max 10 items)
    sections = [{"title": "Section", "rows": [{"id": "row_id", "title": "Row Title", "description": "optional"}]}]
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages",
            headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"},
            json={
                "messaging_product": "whatsapp",
                "to": to,
                "type": "interactive",
                "interactive": {
                    "type": "list",
                    "body": {"text": text},
                    "action": {
                        "button": button_text,
                        "sections": sections
                    }
                }
            }
        )
        print(f"WhatsApp send list: {response.status_code}")
        if response.status_code != 200:
            print(f"List error: {response.text}")
            # Fallback to text
            fallback = text + "\n\n"
            for section in sections:
                for i, row in enumerate(section["rows"], 1):
                    fallback += f"{i}. {row['title']}\n"
            fallback += "\nMeharbani kar ke number likhein."
            await send_message(to, fallback)


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
        return await upload_public_image(
            img_response.content,
            img_response.headers.get("Content-Type"),
        )


# ══════════════════════════════════════════════════════
# MENU SENDERS
# ══════════════════════════════════════════════════════

async def send_welcome_menu(to: str):
    """Send welcome message with register/status buttons"""
    await send_buttons(
        to,
        "🏪 *Find X Marketplace*\n\nAssalam o Alaikum! 👋\nLahore ke hyperlocal marketplace mein khush amdeed!\n\nAap kya karna chahte hain?",
        [
            {"id": "btn_register", "title": "🏪 Store Register Karen"},
            {"id": "btn_status",   "title": "📊 Store Status Check"},
        ]
    )


async def send_store_menu(to: str, store_name: str):
    """Send verified seller store management menu"""
    await send_list(
        to,
        f"🏪 *{store_name}*\n✅ Verified Store\n\nAap kya karna chahte hain?\n_(Neeche button dabayein)_",
        "📋 Options Dekhein",
        [{
            "title": "Store Management",
            "rows": [
                {"id": "menu_add",    "title": "➕ Product Add Karen",    "description": "Naya product list karein"},
                {"id": "menu_view",   "title": "📦 Mere Products",        "description": "Apni listings dekhein"},
                {"id": "menu_price",  "title": "✏️ Price Update Karen",   "description": "Product ka price badlein"},
                {"id": "menu_delete", "title": "🗑️ Product Delete Karen", "description": "Listing hatayein"},
            ]
        }]
    )


async def send_main_menu_button(to: str):
    """Send a simple main menu button"""
    await send_buttons(
        to,
        "Aur kuch karna hai?",
        [{"id": "btn_main_menu", "title": "🏠 Main Menu"}]
    )


async def send_cancel_back_buttons(to: str, text: str):
    """Send message with cancel button"""
    await send_buttons(
        to,
        text,
        [{"id": "btn_cancel", "title": "❌ Cancel"}]
    )


# ══════════════════════════════════════════════════════
# AREA LIST
# ══════════════════════════════════════════════════════

AREAS = {
    "area_1":  "DHA (Defence)",
    "area_2":  "Gulberg",
    "area_3":  "Model Town",
    "area_4":  "Johar Town",
    "area_5":  "Township",
    "area_6":  "Garden Town",
    "area_7":  "Faisal Town",
    "area_8":  "Cantt",
    "area_9":  "Bahria Town",
    "area_10": "Iqbal Town",
    "area_11": "Wapda Town",
    "area_12": "Valencia Town",
    "area_13": "Askari",
    "area_14": "Walled City",
    "area_15": "Anarkali",
    "area_16": "Mall Road",
    "area_17": "Shadman",
    "area_18": "Samanabad",
    "area_19": "Shahdara",
    "area_20": "Raiwind",
    "area_21": "Thokar Niaz Baig",
    "area_22": "Multan Road",
    "area_23": "Ferozepur Road",
    "area_24": "Wagah",
    "area_25": "Ichhra",
    "area_26": "Other",
}

async def send_area_list(to: str):
    """Send area selection list"""
    rows = [{"id": k, "title": v} for k, v in AREAS.items()]
    # Split into 2 sections (max 10 per section)
    await send_list(
        to,
        "Lahore mein aap ka store kis area mein hai?\nMeharbani kar ke apna area select karein:",
        "📍 Area Select Karen",
        [
            {"title": "Areas (1-13)", "rows": rows[:13]},
            {"title": "Areas (14-26)", "rows": rows[13:]},
        ]
    )


# ══════════════════════════════════════════════════════
# MAIN MESSAGE HANDLER
# ══════════════════════════════════════════════════════

async def handle_message(sender: str, text: str, media_id: str = None, location: dict = None, interactive_id: str = None):
    session = await get_session(sender)
    step    = session.get("step", "idle")

    # Use interactive button/list ID if available
    if interactive_id:
        text = interactive_id

    print(f"Message from {sender}: text='{text}', interactive='{interactive_id}', step={step}")
    print(f"After processing: text='{text}', interactive_id='{interactive_id}', step='{step}'")

    # ── GLOBAL RESETS ────────────────────────────────
    if text.strip().lower() in ["m", "menu", "btn_main_menu"] or interactive_id == "btn_main_menu":
        await clear_session(sender)
        step = "idle"
        session = {"step": "idle"}

    if text.strip().lower() in ["cancel", "btn_cancel", "c"] or interactive_id == "btn_cancel":
        await clear_session(sender)
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Store).where(
                    Store.whatsapp_number == sender,
                    Store.is_active == True
                )
            )
            existing = result.scalar_one_or_none()

        if existing and existing.is_verified:
            await send_store_menu(sender, existing.name)
        else:
            await send_buttons(
                sender,
                "❌ *Cancel Ho Gaya*",
                [
                    {"id": "btn_register",  "title": "🏪 Register Karen"},
                    {"id": "btn_main_menu", "title": "🏠 Main Menu"},
                ]
            )
        return

    # ══════════════════════════════════════════════════
    # WELCOME — hi/hello/register/r
    # ══════════════════════════════════════════════════
    if text.strip().lower() in ["hi", "hello", "start", "register", "r", "مرحبا"] or step == "idle" and not text:

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Store).where(
                    Store.whatsapp_number == sender,
                    Store.is_active == True
                )
            )
            existing = result.scalar_one_or_none()

        if existing:
            if existing.is_verified:
                await send_store_menu(sender, existing.name)
            else:
                await send_buttons(
                    sender,
                    f"👋 Wapas khush amdeed!\n\n🏪 *{existing.name}*\n⏳ Status: Admin approval ka intezaar hai\n\nHamari team 24 ghante mein review karegi.",
                    [{"id": "btn_main_menu", "title": "🏠 Main Menu"}]
                )
            return

        await send_welcome_menu(sender)
        session = {"step": "reg_start"}
        await save_session(sender, session)
        return

    # ══════════════════════════════════════════════════
    # REGISTRATION FLOW
    # ══════════════════════════════════════════════════

    elif step == "reg_start" or text in ["btn_register", "btn_status"]:

        if text == "btn_status":
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Store).where(Store.whatsapp_number == sender)
                )
                store = result.scalar_one_or_none()
            if store:
                status = "✅ Verified & Active" if store.is_verified and store.is_active else "⏳ Pending Approval"
                await send_buttons(
                    sender,
                    f"🏪 *{store.name}*\n\n📊 Status: {status}\n📍 Area: {store.city or 'Set nahi'}\n\nHamari team jald review karegi!",
                    [{"id": "btn_main_menu", "title": "🏠 Main Menu"}]
                )
            else:
                await send_welcome_menu(sender)
                session = {"step": "reg_start"}
                await save_session(sender, session)
            await clear_session(sender)
            return

        # Start registration
        session = {"step": "reg_name"}
        await save_session(sender, session)
        await send_cancel_back_buttons(
            sender,
            "🏪 *Store Registration*\n━━━━━━━━━━━━━━━\nStep 1/6 — Aap ka Naam\n━━━━━━━━━━━━━━━\n\nApna poora naam likhein:\n_(Sirf huroof — numbers ya symbols nahi)_"
        )

    elif step == "reg_name":
        import re
        if not text or not re.match(r'^[a-zA-Z\s\u0600-\u06FF]+$', text.strip()):
            await send_cancel_back_buttons(
                sender,
                "⚠️ *Galat Input!*\n\nNaam mein sirf huroof hon chahiye.\n✅ Misaal: Ahmed Ali\n❌ Nahi: 123abc\n\nMeharbani kar ke dobara apna naam likhein:"
            )
            return
        if len(text.strip()) < 3:
            await send_cancel_back_buttons(
                sender,
                "⚠️ Naam kam az kam 3 characters ka hona chahiye.\n\nDobara apna naam likhein:"
            )
            return
        session["owner_name"] = text.strip().title()
        session["step"]       = "reg_store_name"
        await save_session(sender, session)
        await send_cancel_back_buttons(
            sender,
            f"🏪 *Store Registration*\n━━━━━━━━━━━━━━━\nStep 2/6 — Store ka Naam\n━━━━━━━━━━━━━━━\n\n{session['owner_name']}, aap se mil ke khushi hui! 👋\n\nApne store ka naam likhein:\n_(Huroof aur numbers allowed hain)_"
        )

    elif step == "reg_store_name":
        import re
        if not text or not re.match(r'^[a-zA-Z0-9\s\u0600-\u06FF]+$', text.strip()):
            await send_cancel_back_buttons(
                sender,
                "⚠️ *Galat Input!*\n\nStore naam mein special characters nahi hon chahiye.\n✅ Misaal: Ahmed Store\n❌ Nahi: Ahmed@Store!\n\nMeharbani kar ke dobara store ka naam likhein:"
            )
            return
        if len(text.strip()) < 3:
            await send_cancel_back_buttons(
                sender,
                "⚠️ Store naam kam az kam 3 characters ka hona chahiye.\n\nDobara store ka naam likhein:"
            )
            return
        session["store_name"] = text.strip().title()
        session["step"]       = "reg_category"
        await save_session(sender, session)
        await send_buttons(
            sender,
            f"🏪 *Store Registration*\n━━━━━━━━━━━━━━━\nStep 3/6 — Category\n━━━━━━━━━━━━━━━\n\n✅ Store: *{session['store_name']}*\n\nAap ka store kis qisam ka hai?",
            [
                {"id": "cat_products",   "title": "📦 Products"},
                {"id": "cat_services",   "title": "🔧 Services"},
                {"id": "cat_restaurant", "title": "🍽️ Restaurant"},
            ]
        )
        # Send hotel as separate message since max 3 buttons
        await send_buttons(
            sender,
            "Ya phir:",
            [
                {"id": "cat_hotel",  "title": "🏨 Hotel"},
                {"id": "btn_cancel", "title": "❌ Cancel"},
            ]
        )

    elif step == "reg_category":
        cats = {
            "cat_products":   "products",
            "cat_services":   "services",
            "cat_restaurant": "restaurant",
            "cat_hotel":      "hotel",
            # Text fallback
            "1": "products", "2": "services", "3": "restaurant", "4": "hotel",
        }
        if text not in cats:
            await send_buttons(
                sender,
                "⚠️ Meharbani kar ke upar diye gaye buttons mein se ek select karein!",
                [
                    {"id": "cat_products",   "title": "📦 Products"},
                    {"id": "cat_services",   "title": "🔧 Services"},
                    {"id": "cat_restaurant", "title": "🍽️ Restaurant"},
                ]
            )
            await send_buttons(
                sender,
                "Ya phir:",
                [
                    {"id": "cat_hotel",  "title": "🏨 Hotel"},
                    {"id": "btn_cancel", "title": "❌ Cancel"},
                ]
            )
            return
        session["category"] = cats[text]
        session["step"]     = "reg_city"
        await save_session(sender, session)
        await send_area_list(sender)

    elif step == "reg_city":
        if text not in AREAS and text not in [str(i) for i in range(1, 27)]:
            await send_area_list(sender)
            return
        # Handle both button ID and number fallback
        if text in AREAS:
            session["city"] = AREAS[text]
        else:
            area_list = list(AREAS.values())
            session["city"] = area_list[int(text) - 1]

        session["step"] = "reg_location"
        await save_session(sender, session)
        await send_cancel_back_buttons(
            sender,
            f"🏪 *Store Registration*\n━━━━━━━━━━━━━━━\nStep 5/6 — Location 📍\n━━━━━━━━━━━━━━━\n\n✅ Area: *{session['city']}*\n\nAb apni store ki exact location share karein taake buyers GPS se aapko dhoond sakein! 🗺️\n\nYeh kaise karein:\n1️⃣ Neeche 📎 button dabayein\n2️⃣ *Location* select karein\n3️⃣ *Send Your Current Location* dabayein\n   Ya map pe apni store pin karein\n4️⃣ Send kar dein!\n\n⚠️ Location zaroori hai!"
        )

    elif step == "reg_location":
        if location:
            session["lat"] = location.get("latitude")
            session["lng"] = location.get("longitude")
            session["step"] = "reg_password"
            await save_session(sender, session)
            await send_cancel_back_buttons(
                sender,
                f"🏪 *Store Registration*\n━━━━━━━━━━━━━━━\nStep 6/6 — Password\n━━━━━━━━━━━━━━━\n\n✅ Location mil gayi! 📍\n\nBas thoda aur! 🎉\n\nWebsite login ke liye password set karein:\n⚠️ Kam az kam 6 characters"
            )
        else:
            await send_cancel_back_buttons(
                sender,
                "⚠️ *Location Pin Nahi Mili!*\n\nMeharbani kar ke 📍 location PIN share karein.\nText se location accept nahi hogi!\n\n📎 → Location → Send Current Location"
            )

    elif step == "reg_password":
        if len(text.strip()) < 6:
            await send_cancel_back_buttons(
                sender,
                "⚠️ *Password Bohat Chota Hai!*\n\nKam az kam 6 characters ka hona chahiye.\n\nMeharbani kar ke dobara password likhein:"
            )
            return
        session["password"] = text.strip()
        session["step"] = "reg_confirm"
        await save_session(sender, session)
        await send_cancel_back_buttons(
            sender,
            "Password confirm karein:\nDobara same password likhein:"
        )

    elif step == "reg_confirm":
        if text.strip() != session.get("password"):
            await send_cancel_back_buttons(
                sender,
                "⚠️ *Password Match Nahi Hua!*\n\nDobara pehla password likhein:"
            )
            session["step"] = "reg_password"
            await save_session(sender, session)
            return

        # Save everything
        async with AsyncSessionLocal() as db:
            check = await db.execute(
                select(Store).where(
                    Store.whatsapp_number == sender,
                    Store.is_active == True
                )
            )
            if check.scalar_one_or_none():
                await clear_session(sender)
                await send_message(
                    sender,
                    "❌ Is number pe pehle se ek store registered hai.\n\nApna store manage karne ke liye *M* likhein."
                )
                return

            result = await db.execute(select(User).where(User.phone == sender))
            user = result.scalar_one_or_none()

            from app.services.supabase_auth import create_auth_user
            if not user:
                auth_user = await create_auth_user(
                    phone=sender,
                    password=session["password"],
                    name=session["owner_name"],
                    role="seller",
                )
                user = User(
                    phone=sender,
                    supabase_user_id=auth_user["id"],
                    name=session["owner_name"],
                    role="seller",
                )
                db.add(user)
                await db.flush()
            else:
                user.role = "seller"
                if not user.supabase_user_id:
                    auth_user = await create_auth_user(
                        phone=sender,
                        password=session["password"],
                        name=user.name or session["owner_name"],
                        role="seller",
                    )
                    user.supabase_user_id = auth_user["id"]

            store = Store(
                owner_id=user.id,
                name=session["store_name"],
                description=session.get("description", ""),
                category=session["category"],
                city=session["city"],
                lat=session.get("lat"),
                lng=session.get("lng"),
                whatsapp_number=sender,
                is_verified=False
            )
            db.add(store)
            await db.commit()

        await clear_session(sender)
        await send_buttons(
            sender,
            f"✅ *Store Submit Ho Gaya!*\n━━━━━━━━━━━━━━━\n🏪 {session['store_name']}\n📍 {session['city']}\n\nHamari team 24 ghante mein review karegi!\n\n🌐 Website Login:\n📱 Phone: {sender}\n🔑 Password: aap ka set kiya hua\n🔗 hyperlocal-marketplace-zeta.vercel.app",
            [{"id": "btn_main_menu", "title": "🏠 Main Menu"}]
        )

    # ══════════════════════════════════════════════════
    # MAIN MENU — M / menu
    # ══════════════════════════════════════════════════

    elif text.strip().lower() in ["m", "menu", "btn_main_menu"]:
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
            await send_buttons(
                sender,
                "⚠️ Aap ka store abhi verify nahi hua.\nAdmin approval ka intezaar karein.\n\nAgar registered nahi hain toh hi likhein.",
                [{"id": "btn_register", "title": "🏪 Register Karen"}]
            )
            return

        await send_store_menu(sender, store.name)

    # ══════════════════════════════════════════════════
    # ADD PRODUCT FLOW
    # ══════════════════════════════════════════════════

    elif text in ["menu_add", "add product"] or "product add" in text.lower():
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
            await send_message(sender, "⚠️ Aap ka store verify nahi hua. Admin approval ka intezaar karein.")
            return

        session = {"step": "add_title"}
        await save_session(sender, session)
        await send_cancel_back_buttons(
            sender,
            "➕ *Product Add Karen*\n━━━━━━━━━━━━━━━\nStep 1/4 — Product Naam\n━━━━━━━━━━━━━━━\n\nProduct ya service ka naam likhein:"
        )

    elif step == "add_title":
        if not text or len(text.strip()) < 2:
            await send_cancel_back_buttons(
                sender,
                "⚠️ Naam zaroori hai!\n\nMeharbani kar ke product ka naam likhein:"
            )
            return
        session["title"] = text.strip().title()
        session["step"]  = "add_price"
        await save_session(sender, session)
        await send_cancel_back_buttons(
            sender,
            f"➕ *Product Add Karen*\n━━━━━━━━━━━━━━━\nStep 2/4 — Price\n━━━━━━━━━━━━━━━\n\n✅ Product: *{session['title']}*\n\nPKR mein price likhein:\n_(Sirf number — misaal: 850)_"
        )

    elif step == "add_price":
        try:
            price = float(text.replace(",", "").replace("rs", "").replace("pkr", "").strip())
            if price <= 0:
                raise ValueError
            session["price"] = price
        except:
            await send_cancel_back_buttons(
                sender,
                "⚠️ *Galat Input!*\n\nSirf number likhein.\n✅ Misaal: 850\n❌ Nahi: PKR850 ya 850rs\n\nMeharbani kar ke dobara price likhein:"
            )
            return
        session["step"] = "add_description"
        await save_session(sender, session)
        await send_buttons(
            sender,
            f"➕ *Product Add Karen*\n━━━━━━━━━━━━━━━\nStep 3/4 — Description\n━━━━━━━━━━━━━━━\n\n✅ Price: PKR {int(price)}\n\nMukhtasar description likhein:",
            [
                {"id": "skip_desc",  "title": "⏭️ Skip"},
                {"id": "btn_cancel", "title": "❌ Cancel"},
            ]
        )

    elif step == "add_description":
        session["description"] = "" if text in ["skip", "skip_desc"] else text
        session["step"]        = "add_image"
        await save_session(sender, session)
        await send_buttons(
            sender,
            "➕ *Product Add Karen*\n━━━━━━━━━━━━━━━\nStep 4/4 — Photo 📸\n━━━━━━━━━━━━━━━\n\nProduct ki photo bhejein:",
            [
                {"id": "skip_image", "title": "⏭️ Skip"},
                {"id": "btn_cancel", "title": "❌ Cancel"},
            ]
        )

    elif step == "add_image":
        image_url = None
        if media_id:
            try:
                image_url = await download_and_upload_image(media_id)
            except Exception as e:
                print(f"Image upload error: {e}")
        elif text in ["skip", "skip_image"]:
            pass
        else:
            await send_buttons(
                sender,
                "⚠️ Photo nahi mili!\nMeharbani kar ke image bhejein ya skip karein.",
                [
                    {"id": "skip_image", "title": "⏭️ Skip"},
                    {"id": "btn_cancel", "title": "❌ Cancel"},
                ]
            )
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
                await send_message(sender, "Store nahi mila.")
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

        await clear_session(sender)
        await send_buttons(
            sender,
            f"✅ *Product Add Ho Gaya!*\n━━━━━━━━━━━━━━━\n🍽️ {session['title']}\n💰 PKR {int(session['price'])}\n\nAur kya karna hai?",
            [
                {"id": "menu_add",    "title": "➕ Aur Add Karen"},
                {"id": "menu_view",   "title": "📦 Products Dekhein"},
                {"id": "btn_main_menu", "title": "🏠 Main Menu"},
            ]
        )

    # ══════════════════════════════════════════════════
    # VIEW PRODUCTS
    # ══════════════════════════════════════════════════

    elif text in ["menu_view", "my products"] or "mere products" in text.lower():
        async with AsyncSessionLocal() as db:
            store_result = await db.execute(
                select(Store).where(
                    Store.whatsapp_number == sender,
                    Store.is_active == True
                )
            )
            store = store_result.scalar_one_or_none()
            if not store:
                await send_message(sender, "Koi store nahi mila. *hi* likhein.")
                return

            listings_result = await db.execute(
                select(Listing).where(
                    Listing.store_id == store.id,
                    Listing.is_available == True
                )
            )
            items = listings_result.scalars().all()

        if not items:
            await send_buttons(
                sender,
                "📦 Aap ka koi active product nahi hai.",
                [
                    {"id": "menu_add",      "title": "➕ Product Add Karen"},
                    {"id": "btn_main_menu", "title": "🏠 Main Menu"},
                ]
            )
            return

        msg = f"📦 *Aap ke Products ({len(items)}):*\n━━━━━━━━━━━━━━━\n\n"
        for i, item in enumerate(items, 1):
            msg += f"{i}. {item.title} — PKR {int(item.price)}\n"

        await send_buttons(
            sender,
            msg,
            [
                {"id": "menu_add",      "title": "➕ Product Add Karen"},
                {"id": "btn_main_menu", "title": "🏠 Main Menu"},
            ]
        )

    # ══════════════════════════════════════════════════
    # DELETE PRODUCT
    # ══════════════════════════════════════════════════

    elif text in ["menu_delete", "delete product"] or "product delete" in text.lower():
        async with AsyncSessionLocal() as db:
            store_result = await db.execute(
                select(Store).where(
                    Store.whatsapp_number == sender,
                    Store.is_active == True
                )
            )
            store = store_result.scalar_one_or_none()
            if not store:
                await send_message(sender, "Koi store nahi mila.")
                return

            listings_result = await db.execute(
                select(Listing).where(
                    Listing.store_id == store.id,
                    Listing.is_available == True
                )
            )
            items = listings_result.scalars().all()

        if not items:
            await send_buttons(
                sender,
                "📦 Delete karne ke liye koi product nahi hai.",
                [{"id": "btn_main_menu", "title": "🏠 Main Menu"}]
            )
            return

        # Send list of products to delete
        rows = [
            {"id": f"del_{item.id}", "title": item.title, "description": f"PKR {int(item.price)}"}
            for item in items
        ]
        session = {
            "step":  "confirm_delete",
            "items": [{"id": str(item.id), "title": item.title} for item in items]
        }
        await save_session(sender, session)
        await send_list(
            sender,
            "🗑️ *Product Delete Karen*\n━━━━━━━━━━━━━━━\nKaunsa product delete karna chahte hain?\n\nSelect karne ke baad cancel ke liye *C* likhein.",
            "🗑️ Product Select Karen",
            [{"title": "Aap ke Products", "rows": rows[:10]}]
        )
        await send_buttons(
            sender,
            "Ya wapas jayein:",
            [
                {"id": "btn_cancel",    "title": "❌ Cancel"},
                {"id": "btn_main_menu", "title": "🏠 Main Menu"},
            ]
        )

    elif step == "confirm_delete":
        # Handle list selection
        if text.startswith("del_"):
            product_id = text.replace("del_", "")
            items = session.get("items", [])
            selected = next((i for i in items if i["id"] == product_id), None)
            if not selected:
                await send_message(sender, "Product nahi mila.")
                return
            session["delete_item"] = selected
            session["step"] = "confirm_delete_yes"
            await save_session(sender, session)
            await send_buttons(
                sender,
                f"⚠️ *Confirm Delete*\n━━━━━━━━━━━━━━━\nKya aap sure hain?\n\n🗑️ *{selected['title']}*\n\nYeh action wapas nahi ho sakta!",
                [
                    {"id": "confirm_yes",   "title": "✅ Haan Delete Karen"},
                    {"id": "confirm_no",    "title": "❌ Nahi Cancel"},
                ]
            )
        # Handle number fallback
        else:
            items = session.get("items", [])
            try:
                index = int(text) - 1
                if index < 0 or index >= len(items):
                    raise ValueError
                selected = items[index]
                session["delete_item"] = selected
                session["step"] = "confirm_delete_yes"
                await save_session(sender, session)
                await send_buttons(
                    sender,
                    f"⚠️ *Confirm Delete*\n━━━━━━━━━━━━━━━\nKya aap sure hain?\n\n🗑️ *{selected['title']}*",
                    [
                        {"id": "confirm_yes", "title": "✅ Haan Delete Karen"},
                        {"id": "confirm_no",  "title": "❌ Nahi Cancel"},
                    ]
                )
            except:
                await send_buttons(
                    sender,
                    f"⚠️ Sahi number likhein (1 se {len(items)} tak)",
                    [{"id": "btn_main_menu", "title": "🏠 Main Menu"}]
                )

    elif step == "confirm_delete_yes":
        if text in ["confirm_yes"]:
            selected = session.get("delete_item")
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Listing).where(Listing.id == selected["id"])
                )
                listing = result.scalar_one_or_none()
                if listing:
                    listing.is_available = False
                    await db.commit()
            await clear_session(sender)
            await send_buttons(
                sender,
                f"✅ *{selected['title']}* delete ho gaya!",
                [
                    {"id": "menu_delete",   "title": "🗑️ Aur Delete Karen"},
                    {"id": "btn_main_menu", "title": "🏠 Main Menu"},
                ]
            )
        else:
            await clear_session(sender)
            await send_buttons(
                sender,
                "❌ Delete cancel ho gaya!",
                [{"id": "btn_main_menu", "title": "🏠 Main Menu"}]
            )

    # ══════════════════════════════════════════════════
    # UPDATE PRICE
    # ══════════════════════════════════════════════════

    elif text in ["menu_price", "update price"] or "price update" in text.lower():
        async with AsyncSessionLocal() as db:
            store_result = await db.execute(
                select(Store).where(
                    Store.whatsapp_number == sender,
                    Store.is_active == True
                )
            )
            store = store_result.scalar_one_or_none()
            if not store:
                await send_message(sender, "Koi store nahi mila.")
                return

            listings_result = await db.execute(
                select(Listing).where(
                    Listing.store_id == store.id,
                    Listing.is_available == True
                )
            )
            items = listings_result.scalars().all()

        if not items:
            await send_buttons(
                sender,
                "📦 Update karne ke liye koi product nahi hai.",
                [{"id": "btn_main_menu", "title": "🏠 Main Menu"}]
            )
            return

        rows = [
            {"id": f"price_{item.id}", "title": item.title, "description": f"PKR {int(item.price)}"}
            for item in items
        ]
        session = {
            "step":  "select_product_price",
            "items": [{"id": str(item.id), "title": item.title, "price": float(item.price)} for item in items]
        }
        await save_session(sender, session)
        await send_list(
            sender,
            "✏️ *Price Update Karen*\n━━━━━━━━━━━━━━━\nKis product ka price update karna chahte hain?\n\nSelect karne ke baad cancel ke liye *C* likhein.",
            "✏️ Product Select Karen",
            [{"title": "Aap ke Products", "rows": rows[:10]}]
        )
        await send_buttons(
            sender,
            "Ya wapas jayein:",
            [
                {"id": "btn_cancel",    "title": "❌ Cancel"},
                {"id": "btn_main_menu", "title": "🏠 Main Menu"},
            ]
        )

    elif step == "select_product_price":
        items = session.get("items", [])
        selected = None

        if text.startswith("price_"):
            product_id = text.replace("price_", "")
            selected = next((i for i in items if i["id"] == product_id), None)
        else:
            try:
                index = int(text) - 1
                if 0 <= index < len(items):
                    selected = items[index]
            except:
                pass

        if not selected:
            await send_buttons(
                sender,
                f"⚠️ Sahi number likhein (1 se {len(items)} tak)",
                [{"id": "btn_main_menu", "title": "🏠 Main Menu"}]
            )
            return

        session["selected_item"] = selected
        session["step"]          = "enter_new_price"
        await save_session(sender, session)
        await send_cancel_back_buttons(
            sender,
            f"✏️ *Price Update Karen*\n━━━━━━━━━━━━━━━\n📦 {selected['title']}\n💰 Purana price: PKR {int(selected['price'])}\n\nNaya price likhein:\n_(Sirf number)_"
        )

    elif step == "enter_new_price":
        try:
            new_price = float(text.replace(",", "").replace("rs", "").replace("pkr", "").strip())
            if new_price <= 0:
                raise ValueError
        except:
            await send_cancel_back_buttons(
                sender,
                "⚠️ *Galat Input!*\n\nSirf number likhein.\n✅ Misaal: 750\n❌ Nahi: PKR750\n\nMeharbani kar ke dobara naya price likhein:"
            )
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
        await send_buttons(
            sender,
            f"✅ *Price Update Ho Gaya!*\n━━━━━━━━━━━━━━━\n📦 {selected['title']}\n💰 Naya price: PKR {int(new_price)}",
            [
                {"id": "menu_price",    "title": "✏️ Aur Update Karen"},
                {"id": "btn_main_menu", "title": "🏠 Main Menu"},
            ]
        )

    # ══════════════════════════════════════════════════
    # UNKNOWN COMMAND
    # ══════════════════════════════════════════════════

    else:
        await send_buttons(
            sender,
            "🤔 *Samajh Nahi Aaya!*\n\nMeharbani kar ke buttons use karein.\n\nYa likhein:\n• *M* — Main Menu\n• *hi* — Naya shuru karein",
            [
                {"id": "btn_main_menu", "title": "🏠 Main Menu"},
                {"id": "btn_register",  "title": "🏪 Register Karen"},
            ]
        )
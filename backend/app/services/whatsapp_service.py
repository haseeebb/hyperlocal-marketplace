import httpx
import os
import re
from app.database import AsyncSessionLocal
from app.models.models import Store, Listing, User
from app.services.supabase_storage import upload_public_image
from sqlalchemy import select
from passlib.context import CryptContext

WHATSAPP_TOKEN  = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_ID")
pwd_context     = CryptContext(schemes=["bcrypt"], deprecated="auto")
sessions        = {}

AREAS = [
    "DHA (Defence)", "Gulberg", "Model Town", "Johar Town", "Township",
    "Garden Town", "Faisal Town", "Cantt", "Bahria Town", "Iqbal Town",
    "Wapda Town", "Valencia Town", "Askari", "Walled City", "Anarkali",
    "Mall Road", "Shadman", "Samanabad", "Shahdara", "Raiwind",
    "Thokar Niaz Baig", "Multan Road", "Ferozepur Road", "Wagah", "Ichhra", "Other"
]

# ── Session helpers ───────────────────────────────────
async def get_session(phone):
    return sessions.get(phone, {"step": "idle"})

async def save_session(phone, data):
    sessions[phone] = data

async def clear_session(phone):
    sessions[phone] = {"step": "idle"}

# ══════════════════════════════════════════════════════
# SEND HELPERS
# ══════════════════════════════════════════════════════

async def _post(payload):
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages",
            headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"},
            json=payload
        )
        print(f"WA send ({payload.get('type','?')}): {r.status_code}")
        if r.status_code != 200:
            print(f"WA error: {r.text}")
        return r

async def send_text(to, text):
    await _post({"messaging_product":"whatsapp","to":to,"type":"text","text":{"body":text}})

async def send_buttons(to, body, buttons):
    r = await _post({
        "messaging_product": "whatsapp", "to": to, "type": "interactive",
        "interactive": {
            "type": "button", "body": {"text": body},
            "action": {"buttons": [
                {"type":"reply","reply":{"id":b["id"],"title":b["title"][:20]}}
                for b in buttons[:3]
            ]}
        }
    })
    if r.status_code != 200:
        msg = body + "\n\n"
        for i,b in enumerate(buttons,1): msg += f"{i}. {b['title']}\n"
        await send_text(to, msg)

async def send_list(to, body, btn_label, rows):
    r = await _post({
        "messaging_product": "whatsapp", "to": to, "type": "interactive",
        "interactive": {
            "type": "list", "body": {"text": body},
            "action": {"button": btn_label[:20], "sections": [{"title":"Options","rows":[
                {"id":row["id"],"title":row["title"][:24],"description":row.get("description","")[:72]}
                for row in rows[:10]
            ]}]}
        }
    })
    if r.status_code != 200:
        msg = body + "\n\n"
        for i,row in enumerate(rows,1): msg += f"{i}. {row['title']}\n"
        msg += "\nMeharbani kar ke number likhein."
        await send_text(to, msg)

# ══════════════════════════════════════════════════════
# REUSABLE UI BLOCKS
# ══════════════════════════════════════════════════════

async def send_welcome(to):
    """New user — only register button"""
    await send_buttons(to,
        "🏪 *Find X Marketplace*\n━━━━━━━━━━━━━━━\nAssalam o Alaikum! 👋\nLahore ke hyperlocal marketplace mein khush amdeed!\n\nApna store register karein aur business online karein! 🚀",
        [{"id":"REG_START","title":"🏪 Store Register Karen"}]
    )

async def send_store_menu(to, store_name):
    await send_list(to,
        f"👋 Khush Amdeed!\n🏪 *{store_name}* ✅\n━━━━━━━━━━━━━━━\nAap kya karna chahte hain?\n_(Neeche list dabayein)_",
        "📋 Menu Kholo",
        [{"id":"MENU_ADD",   "title":"➕ Product Add Karen",   "description":"Naya product list karein"},
         {"id":"MENU_VIEW",  "title":"📦 Mere Products",       "description":"Apni listings dekhein"},
         {"id":"MENU_PRICE", "title":"✏️ Price Update Karen",  "description":"Product ka price badlein"},
         {"id":"MENU_DELETE","title":"🗑️ Product Delete Karen","description":"Listing hatayein"}]
    )

async def send_pending(to, store_name):
    await send_text(to,
        f"⏳ *Store Under Review*\n━━━━━━━━━━━━━━━\n🏪 {store_name}\n\nAap ka store hamari team review kar rahi hai.\nApproval mein 24 ghante lagte hain. Thoda intezaar karein! 🙏"
    )

# MERGED button: Cancel & Main Menu
BTN_CANCEL_MAIN = {"id":"BTN_CANCEL_MAIN","title":"🏠 Cancel & Main Menu"}
BTN_BACK        = {"id":"BTN_BACK","title":"↩️ Wapas"}

async def send_step1_btns(to, text):
    """Step 1 — only Cancel & Main Menu"""
    await send_buttons(to, text, [BTN_CANCEL_MAIN])

async def send_step2_btns(to, text):
    """Step 2 — Back + Cancel & Main Menu"""
    await send_buttons(to, text, [BTN_BACK, BTN_CANCEL_MAIN])

async def send_step3_btns(to, text):
    """Step 3+ — Back + Cancel & Main Menu (same, just alias)"""
    await send_buttons(to, text, [BTN_BACK, BTN_CANCEL_MAIN])

async def send_area_text(to, session):
    """Send all 26 areas as numbered text with single cancel button"""
    msg = f"🏪 *Store Registration*\n━━━━━━━━━━━━━━━\nStep 4/6 — Area\n━━━━━━━━━━━━━━━\n\n✅ Category: *{session.get('category','')}*\n\nLahore mein apna area select karein:\nNumber likhein (1-26)\n\n"
    for i, area in enumerate(AREAS, 1):
        msg += f"{i}. {area}\n"
    await send_buttons(to, msg, [BTN_BACK, BTN_CANCEL_MAIN])

# ══════════════════════════════════════════════════════
# IMAGE HELPER
# ══════════════════════════════════════════════════════

async def download_and_upload_image(media_id):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"https://graph.facebook.com/v19.0/{media_id}",
            headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"})
        media_url = r.json().get("url")
        img = await client.get(media_url, headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"})
        return await upload_public_image(img.content, img.headers.get("Content-Type"))

# ══════════════════════════════════════════════════════
# BACK NAVIGATION
# ══════════════════════════════════════════════════════

BACK_STEP = {
    "reg_store_name":"reg_name", "reg_category":"reg_store_name",
    "reg_city":"reg_category",   "reg_location":"reg_city",
    "reg_password":"reg_location","reg_confirm":"reg_password",
    "add_price":"add_title",     "add_description":"add_price",
    "add_image":"add_description","enter_new_price":"select_product_price",
}

async def resend_step(sender, step, session):
    if step == "reg_name":
        await send_step1_btns(sender,
            "🏪 *Store Registration*\n━━━━━━━━━━━━━━━\nStep 1/6 — Aap ka Naam\n━━━━━━━━━━━━━━━\n\nApna poora naam likhein:\n_(Sirf huroof — numbers ya symbols nahi)_"
        )
    elif step == "reg_store_name":
        await send_step2_btns(sender,
            f"🏪 *Store Registration*\n━━━━━━━━━━━━━━━\nStep 2/6 — Store Naam\n━━━━━━━━━━━━━━━\n\n✅ Naam: *{session.get('owner_name','')}*\n\nStore ka naam likhein:"
        )
    elif step == "reg_category":
        await send_list(sender,
            f"🏪 *Store Registration*\n━━━━━━━━━━━━━━━\nStep 3/6 — Category\n━━━━━━━━━━━━━━━\n\n✅ Store: *{session.get('store_name','')}*\n\nCategory select karein:",
            "🏪 Category Chunein",
            [{"id":"CAT_1","title":"📦 Products","description":"Koi bhi product bechein"},
             {"id":"CAT_2","title":"🔧 Services","description":"Services provide karein"},
             {"id":"CAT_3","title":"🍽️ Restaurant","description":"Khana bechein"},
             {"id":"CAT_4","title":"🏨 Hotel","description":"Rooms / accommodation"}]
        )
        await send_buttons(sender, "Wapas jane ke liye:", [BTN_BACK, BTN_CANCEL_MAIN])
    elif step == "reg_city":
        await send_area_text(sender, session)
    elif step == "reg_location":
        await send_step2_btns(sender,
            f"🏪 *Store Registration*\n━━━━━━━━━━━━━━━\nStep 5/6 — Location 📍\n━━━━━━━━━━━━━━━\n\n✅ Area: *{session.get('city','')}*\n\nStore ki exact location share karein:\n1️⃣ 📎 button dabayein\n2️⃣ *Location* select karein\n3️⃣ *Send Current Location* dabayein\n4️⃣ Send karein!\n\n⚠️ Location zaroori hai!"
        )
    elif step == "reg_password":
        await send_step3_btns(sender,
            "🏪 *Store Registration*\n━━━━━━━━━━━━━━━\nStep 6/6 — Password\n━━━━━━━━━━━━━━━\n\nWebsite login ke liye password set karein:\n⚠️ Kam az kam 6 characters"
        )
    elif step == "add_title":
        await send_step1_btns(sender,
            "➕ *Product Add Karen*\n━━━━━━━━━━━━━━━\nStep 1/4 — Product Naam\n━━━━━━━━━━━━━━━\n\nProduct ya service ka naam likhein:"
        )
    elif step == "add_price":
        await send_step2_btns(sender,
            f"➕ *Product Add Karen*\n━━━━━━━━━━━━━━━\nStep 2/4 — Price\n━━━━━━━━━━━━━━━\n\n✅ Product: *{session.get('title','')}*\n\nPKR mein price likhein:\n_(Sirf number — misaal: 850)_"
        )
    elif step == "add_description":
        await send_buttons(sender,
            f"➕ *Product Add Karen*\n━━━━━━━━━━━━━━━\nStep 3/4 — Description\n━━━━━━━━━━━━━━━\n\n✅ Price: PKR {int(session.get('price',0))}\n\nMukhtasar description likhein:",
            [{"id":"SKIP_DESC","title":"⏭️ Skip"}, BTN_BACK, BTN_CANCEL_MAIN]
        )

async def go_back(sender, session):
    step = session.get("step","idle")
    prev = BACK_STEP.get(step)
    if not prev:
        await clear_session(sender)
        async with AsyncSessionLocal() as db:
            r = await db.execute(select(Store).where(
                Store.whatsapp_number==sender, Store.is_verified==True, Store.is_active==True))
            store = r.scalar_one_or_none()
        if store:
            await send_store_menu(sender, store.name)
        else:
            await send_welcome(sender)
        return
    session["step"] = prev
    await save_session(sender, session)
    await resend_step(sender, prev, session)

# ══════════════════════════════════════════════════════
# MAIN HANDLER
# ══════════════════════════════════════════════════════

async def handle_message(sender, text, media_id=None, location=None, interactive_id=None):
    cmd     = (interactive_id or "").strip() or text.strip()
    session = await get_session(sender)
    step    = session.get("step", "idle")

    print(f"MSG {sender}: text='{text}' cmd='{cmd}' step='{step}'")

    # ── GLOBAL: Cancel & Main Menu (merged) ───────────
    if cmd in ["BTN_CANCEL_MAIN", "cancel", "main", "m", "menu"]:
        await clear_session(sender)
        async with AsyncSessionLocal() as db:
            r = await db.execute(select(Store).where(
                Store.whatsapp_number==sender, Store.is_verified==True, Store.is_active==True))
            store = r.scalar_one_or_none()
        if store:
            await send_store_menu(sender, store.name)
        else:
            await send_welcome(sender)
        return

    # ── GLOBAL: Back ──────────────────────────────────
    elif cmd in ["BTN_BACK", "back"]:
        await go_back(sender, session)
        return

    # ══════════════════════════════════════════════════
    # STEP-BASED HANDLERS
    # ══════════════════════════════════════════════════

    elif step == "idle" and cmd not in ["MENU_ADD","MENU_VIEW","MENU_PRICE","MENU_DELETE"]:
        async with AsyncSessionLocal() as db:
            r = await db.execute(select(Store).where(
                Store.whatsapp_number==sender, Store.is_active==True))
            store = r.scalar_one_or_none()
        if store:
            if store.is_verified:
                await send_store_menu(sender, store.name)
            else:
                await send_pending(sender, store.name)
            return
        await send_welcome(sender)
        session = {"step":"reg_wait"}
        await save_session(sender, session)

    elif step == "reg_wait":
        if cmd != "REG_START":
            await send_welcome(sender)
            return
        session = {"step":"reg_name"}
        await save_session(sender, session)
        await send_step1_btns(sender,
            "🏪 *Store Registration*\n━━━━━━━━━━━━━━━\nStep 1/6 — Aap ka Naam\n━━━━━━━━━━━━━━━\n\nApna poora naam likhein:\n_(Sirf huroof — numbers ya symbols nahi)_"
        )

    elif step == "reg_name":
        t = text.strip()
        if not t or not re.match(r'^[a-zA-Z\s\u0600-\u06FF]+$', t):
            await send_step1_btns(sender,
                "⚠️ *Galat Input!*\n\nNaam mein sirf huroof hon chahiye.\n✅ Misaal: Ahmed Ali\n❌ Nahi: 123abc\n\nMeharbani kar ke apna naam likhein:"
            )
            return
        if len(t) < 3:
            await send_step1_btns(sender, "⚠️ Naam kam az kam 3 characters ka hona chahiye.\n\nDobara naam likhein:")
            return
        session["owner_name"] = t.title()
        session["step"] = "reg_store_name"
        await save_session(sender, session)
        await send_step2_btns(sender,
            f"🏪 *Store Registration*\n━━━━━━━━━━━━━━━\nStep 2/6 — Store Naam\n━━━━━━━━━━━━━━━\n\n{session['owner_name']}, aap se mil ke khushi hui! 👋\n\nApne store ka naam likhein:\n_(Huroof aur numbers allowed)_"
        )

    elif step == "reg_store_name":
        t = text.strip()
        if not t or not re.match(r'^[a-zA-Z0-9\s\u0600-\u06FF]+$', t):
            await send_step2_btns(sender,
                "⚠️ Store naam mein special characters nahi hon chahiye.\n✅ Misaal: Ahmed Store\n\nStore ka naam likhein:"
            )
            return
        if len(t) < 3:
            await send_step2_btns(sender, "⚠️ Store naam kam az kam 3 characters.\n\nDobara likhein:")
            return
        session["store_name"] = t.title()
        session["step"] = "reg_category"
        await save_session(sender, session)
        await resend_step(sender, "reg_category", session)

    elif step == "reg_category":
        cat_map = {"CAT_1":"products","CAT_2":"services","CAT_3":"restaurant","CAT_4":"hotel",
                   "1":"products","2":"services","3":"restaurant","4":"hotel"}
        chosen = cat_map.get(cmd) or cat_map.get(text.strip())
        if not chosen:
            await resend_step(sender, "reg_category", session)
            return
        session["category"] = chosen
        session["step"] = "reg_city"
        await save_session(sender, session)
        await send_area_text(sender, session)

    elif step == "reg_city":
        chosen_area = None
        if text.strip().isdigit():
            idx = int(text.strip()) - 1
            if 0 <= idx < len(AREAS): chosen_area = AREAS[idx]
        if not chosen_area:
            await send_area_text(sender, session)
            return
        session["city"] = chosen_area
        session["step"] = "reg_location"
        await save_session(sender, session)
        await send_step2_btns(sender,
            f"🏪 *Store Registration*\n━━━━━━━━━━━━━━━\nStep 5/6 — Location 📍\n━━━━━━━━━━━━━━━\n\n✅ Area: *{chosen_area}*\n\nStore ki exact location share karein taake buyers GPS se dhoond sakein! 🗺️\n\n1️⃣ 📎 button dabayein\n2️⃣ *Location* select karein\n3️⃣ *Send Current Location* dabayein\n4️⃣ Send karein!\n\n⚠️ Location zaroori hai!"
        )

    elif step == "reg_location":
        if location:
            session["lat"] = location.get("latitude")
            session["lng"] = location.get("longitude")
            session["step"] = "reg_password"
            await save_session(sender, session)
            await send_step3_btns(sender,
                "🏪 *Store Registration*\n━━━━━━━━━━━━━━━\nStep 6/6 — Password\n━━━━━━━━━━━━━━━\n\n✅ Location mil gayi! 📍\nBas thoda aur! 🎉\n\nWebsite login ke liye password set karein:\n⚠️ Kam az kam 6 characters"
            )
        else:
            await send_step2_btns(sender,
                "⚠️ *Location Pin Nahi Mili!*\n\nMeharbani kar ke 📍 location PIN share karein.\nText se location accept nahi hogi!\n\n📎 → Location → Send Current Location"
            )

    elif step == "reg_password":
        t = text.strip()
        if len(t) < 6:
            await send_step3_btns(sender,
                "⚠️ Password kam az kam 6 characters ka hona chahiye.\n\nMeharbani kar ke dobara likhein:"
            )
            return
        session["password"] = t
        session["step"] = "reg_confirm"
        await save_session(sender, session)
        await send_step3_btns(sender, "Password confirm karein:\nDobara same password likhein:")

    elif step == "reg_confirm":
        if text.strip() != session.get("password"):
            await send_step3_btns(sender, "⚠️ *Password Match Nahi Hua!*\n\nDobara pehla password likhein:")
            session["step"] = "reg_password"
            await save_session(sender, session)
            return
        try:
            async with AsyncSessionLocal() as db:
                check = await db.execute(select(Store).where(
                    Store.whatsapp_number==sender, Store.is_active==True))
                if check.scalar_one_or_none():
                    await clear_session(sender)
                    await send_text(sender, "❌ Is number pe pehle se store registered hai.")
                    return
                r = await db.execute(select(User).where(User.phone==sender))
                user = r.scalar_one_or_none()
                hashed = pwd_context.hash(session["password"])
                if not user:
                    user = User(phone=sender, name=session["owner_name"], role="seller", hashed_password=hashed)
                    db.add(user)
                    await db.flush()
                else:
                    user.role = "seller"
                    user.hashed_password = hashed
                store = Store(
                    owner_id=user.id, name=session["store_name"], description="",
                    category=session["category"], city=session["city"],
                    lat=session.get("lat"), lng=session.get("lng"),
                    whatsapp_number=sender, is_verified=False, is_active=True,
                )
                db.add(store)
                await db.commit()
            sname = session["store_name"]
            city  = session["city"]
            await clear_session(sender)
            await send_buttons(sender,
                f"✅ *Store Submit Ho Gaya!*\n━━━━━━━━━━━━━━━\n🏪 {sname}\n📍 {city}\n\nHamari team 24 ghante mein review karegi! 🎉\n\n🌐 Website Login:\n📱 Phone: {sender}\n🔑 Password: aap ka set kiya hua\n🔗 hyperlocal-marketplace-zeta.vercel.app/login.html",
                [{"id":"STATUS_CHECK","title":"📊 Status Check Karen"}]
            )
        except Exception as e:
            print(f"Registration error: {e}")
            await send_text(sender, f"❌ Kuch masla hua. Dobara koshish karein.\nError: {str(e)[:100]}")

    # ── ADD PRODUCT STEPS ─────────────────────────────

    elif step == "add_title":
        t = text.strip()
        if not t or len(t) < 2:
            await send_step1_btns(sender, "⚠️ Naam zaroori hai!\n\nProduct ka naam likhein:")
            return
        session["title"] = t.title()
        session["step"]  = "add_price"
        await save_session(sender, session)
        await send_step2_btns(sender,
            f"➕ *Product Add Karen*\n━━━━━━━━━━━━━━━\nStep 2/4 — Price\n━━━━━━━━━━━━━━━\n\n✅ Product: *{session['title']}*\n\nPKR mein price likhein:\n_(Sirf number — misaal: 850)_"
        )

    elif step == "add_price":
        try:
            price = float(text.replace(",","").replace("rs","").replace("pkr","").strip())
            if price <= 0: raise ValueError
        except:
            await send_step2_btns(sender,
                "⚠️ Sirf number likhein.\n✅ Misaal: 850\n❌ Nahi: PKR850\n\nPrice likhein:"
            )
            return
        session["price"] = price
        session["step"]  = "add_description"
        await save_session(sender, session)
        await send_buttons(sender,
            f"➕ *Product Add Karen*\n━━━━━━━━━━━━━━━\nStep 3/4 — Description\n━━━━━━━━━━━━━━━\n\n✅ Price: PKR {int(price)}\n\nMukhtasar description likhein:",
            [{"id":"SKIP_DESC","title":"⏭️ Skip"}, BTN_BACK, BTN_CANCEL_MAIN]
        )

    elif step == "add_description":
        session["description"] = "" if cmd in ["SKIP_DESC","skip"] else text
        session["step"] = "add_image"
        await save_session(sender, session)
        await send_buttons(sender,
            "➕ *Product Add Karen*\n━━━━━━━━━━━━━━━\nStep 4/4 — Photo 📸\n━━━━━━━━━━━━━━━\n\nProduct ki photo bhejein:",
            [{"id":"SKIP_IMG","title":"⏭️ Skip"}, BTN_BACK, BTN_CANCEL_MAIN]
        )

    elif step == "add_image":
        image_url = None
        if media_id:
            try: image_url = await download_and_upload_image(media_id)
            except Exception as e: print(f"Image upload error: {e}")
        elif cmd in ["SKIP_IMG","skip"]:
            pass
        else:
            await send_buttons(sender, "⚠️ Photo nahi mili! Bhejein ya skip karein.",
                [{"id":"SKIP_IMG","title":"⏭️ Skip"}, BTN_CANCEL_MAIN])
            return
        async with AsyncSessionLocal() as db:
            r = await db.execute(select(Store).where(
                Store.whatsapp_number==sender, Store.is_verified==True, Store.is_active==True))
            store = r.scalar_one_or_none()
            if not store:
                await send_text(sender, "Store nahi mila.")
                await clear_session(sender)
                return
            db.add(Listing(store_id=store.id, title=session["title"],
                description=session.get("description",""), price=session["price"],
                currency="PKR", image_url=image_url, is_available=True))
            await db.commit()
        title = session["title"]
        price = session["price"]
        await clear_session(sender)
        await send_buttons(sender,
            f"✅ *Product Add Ho Gaya!*\n━━━━━━━━━━━━━━━\n📦 {title}\n💰 PKR {int(price)}",
            [{"id":"MENU_ADD","title":"➕ Aur Add Karen"},
             {"id":"MENU_VIEW","title":"📦 Products Dekhein"},
             BTN_CANCEL_MAIN]
        )

    # ── PRICE UPDATE STEPS ────────────────────────────

    elif step == "select_product_price":
        items = session.get("items", [])
        selected = None
        if text.strip().isdigit():
            idx = int(text.strip()) - 1
            if 0 <= idx < len(items): selected = items[idx]
        if not selected:
            msg = "⚠️ Sahi number likhein:\n\n"
            for i,item in enumerate(items,1): msg += f"{i}. {item['title']} — PKR {int(item['price'])}\n"
            await send_buttons(sender, msg, [BTN_CANCEL_MAIN])
            return
        session["selected_item"] = selected
        session["step"] = "enter_new_price"
        await save_session(sender, session)
        await send_step2_btns(sender,
            f"✏️ *Price Update Karen*\n━━━━━━━━━━━━━━━\n📦 {selected['title']}\n💰 Purana price: PKR {int(selected['price'])}\n\nNaya price likhein:\n_(Sirf number)_"
        )

    elif step == "enter_new_price":
        try:
            new_price = float(text.replace(",","").replace("rs","").replace("pkr","").strip())
            if new_price <= 0: raise ValueError
        except:
            await send_step2_btns(sender, "⚠️ Sirf number likhein.\n✅ Misaal: 750\n\nNaya price likhein:")
            return
        selected = session.get("selected_item")
        async with AsyncSessionLocal() as db:
            r = await db.execute(select(Listing).where(Listing.id==selected["id"]))
            listing = r.scalar_one_or_none()
            if listing:
                listing.price = new_price
                await db.commit()
        await clear_session(sender)
        await send_buttons(sender,
            f"✅ *Price Update Ho Gaya!*\n━━━━━━━━━━━━━━━\n📦 {selected['title']}\n💰 Naya price: PKR {int(new_price)}",
            [{"id":"MENU_PRICE","title":"✏️ Aur Update Karen"}, BTN_CANCEL_MAIN]
        )

    # ── DELETE STEPS ──────────────────────────────────

    elif step == "confirm_delete":
        items = session.get("items", [])
        selected = None
        if text.strip().isdigit():
            idx = int(text.strip()) - 1
            if 0 <= idx < len(items): selected = items[idx]
        if not selected:
            msg = "⚠️ Sahi number likhein:\n\n"
            for i,item in enumerate(items,1): msg += f"{i}. {item['title']}\n"
            await send_buttons(sender, msg, [BTN_CANCEL_MAIN])
            return
        session["delete_item"] = selected
        session["step"] = "confirm_delete_yes"
        await save_session(sender, session)
        await send_buttons(sender,
            f"⚠️ *Confirm Delete*\n━━━━━━━━━━━━━━━\nKya aap sure hain?\n\n🗑️ *{selected['title']}*\n\nYeh wapas nahi ho sakta!",
            [{"id":"CONFIRM_YES","title":"✅ Haan Delete Karen"}, BTN_CANCEL_MAIN]
        )

    elif step == "confirm_delete_yes":
        if cmd == "CONFIRM_YES":
            selected = session.get("delete_item")
            async with AsyncSessionLocal() as db:
                r = await db.execute(select(Listing).where(Listing.id==selected["id"]))
                listing = r.scalar_one_or_none()
                if listing:
                    listing.is_available = False
                    await db.commit()
            await clear_session(sender)
            await send_buttons(sender,
                f"✅ *{selected['title']}* delete ho gaya!",
                [{"id":"MENU_DELETE","title":"🗑️ Aur Delete Karen"}, BTN_CANCEL_MAIN]
            )
        else:
            await clear_session(sender)
            async with AsyncSessionLocal() as db:
                r = await db.execute(select(Store).where(
                    Store.whatsapp_number==sender, Store.is_verified==True, Store.is_active==True))
                store = r.scalar_one_or_none()
            if store: await send_store_menu(sender, store.name)

    # ══════════════════════════════════════════════════
    # MENU COMMANDS (after all step handlers)
    # ══════════════════════════════════════════════════

    elif cmd == "MENU_ADD":
        async with AsyncSessionLocal() as db:
            r = await db.execute(select(Store).where(
                Store.whatsapp_number==sender, Store.is_verified==True, Store.is_active==True))
            store = r.scalar_one_or_none()
        if not store:
            await send_text(sender, "⚠️ Aap ka store verify nahi hua.")
            return
        session = {"step":"add_title"}
        await save_session(sender, session)
        await send_step1_btns(sender,
            "➕ *Product Add Karen*\n━━━━━━━━━━━━━━━\nStep 1/4 — Product Naam\n━━━━━━━━━━━━━━━\n\nProduct ya service ka naam likhein:"
        )

    elif cmd == "MENU_VIEW":
        async with AsyncSessionLocal() as db:
            r = await db.execute(select(Store).where(Store.whatsapp_number==sender, Store.is_active==True))
            store = r.scalar_one_or_none()
            if not store:
                await send_text(sender, "Koi store nahi mila.")
                return
            lr = await db.execute(select(Listing).where(Listing.store_id==store.id, Listing.is_available==True))
            items = lr.scalars().all()
        if not items:
            await send_buttons(sender, "📦 Aap ka koi active product nahi hai.",
                [{"id":"MENU_ADD","title":"➕ Product Add Karen"}, BTN_CANCEL_MAIN])
            return
        msg = f"📦 *Aap ke Products ({len(items)}):*\n━━━━━━━━━━━━━━━\n\n"
        for i,item in enumerate(items,1): msg += f"{i}. {item.title} — PKR {int(item.price)}\n"
        await send_buttons(sender, msg,
            [{"id":"MENU_ADD","title":"➕ Product Add Karen"}, BTN_CANCEL_MAIN])

    elif cmd == "MENU_PRICE":
        async with AsyncSessionLocal() as db:
            r = await db.execute(select(Store).where(Store.whatsapp_number==sender, Store.is_active==True))
            store = r.scalar_one_or_none()
            if not store:
                await send_text(sender, "Koi store nahi mila.")
                return
            lr = await db.execute(select(Listing).where(Listing.store_id==store.id, Listing.is_available==True))
            items = lr.scalars().all()
        if not items:
            await send_buttons(sender, "📦 Update karne ke liye koi product nahi hai.", [BTN_CANCEL_MAIN])
            return
        msg = "✏️ *Price Update Karen*\n━━━━━━━━━━━━━━━\nKis product ka price update karna chahte hain?\nNumber likhein:\n\n"
        for i,item in enumerate(items,1): msg += f"{i}. {item.title} — PKR {int(item.price)}\n"
        session = {"step":"select_product_price",
                   "items":[{"id":str(i.id),"title":i.title,"price":float(i.price)} for i in items]}
        await save_session(sender, session)
        await send_buttons(sender, msg, [BTN_CANCEL_MAIN])

    elif cmd == "MENU_DELETE":
        async with AsyncSessionLocal() as db:
            r = await db.execute(select(Store).where(Store.whatsapp_number==sender, Store.is_active==True))
            store = r.scalar_one_or_none()
            if not store:
                await send_text(sender, "Koi store nahi mila.")
                return
            lr = await db.execute(select(Listing).where(Listing.store_id==store.id, Listing.is_available==True))
            items = lr.scalars().all()
        if not items:
            await send_buttons(sender, "📦 Delete karne ke liye koi product nahi hai.", [BTN_CANCEL_MAIN])
            return
        msg = "🗑️ *Product Delete Karen*\n━━━━━━━━━━━━━━━\nKaunsa product delete karna chahte hain?\nNumber likhein:\n\n"
        for i,item in enumerate(items,1): msg += f"{i}. {item.title} — PKR {int(item.price)}\n"
        session = {"step":"confirm_delete",
                   "items":[{"id":str(i.id),"title":i.title} for i in items]}
        await save_session(sender, session)
        await send_buttons(sender, msg, [BTN_CANCEL_MAIN])

    elif cmd == "STATUS_CHECK":
        async with AsyncSessionLocal() as db:
            r = await db.execute(select(Store).where(Store.whatsapp_number==sender))
            store = r.scalar_one_or_none()
        if store:
            status = "✅ Verified & Active" if store.is_verified else "⏳ Pending Approval"
            await send_buttons(sender,
                f"🏪 *{store.name}*\n📊 Status: {status}\n📍 Area: {store.city or 'Set nahi'}",
                [BTN_CANCEL_MAIN])
        else:
            await send_buttons(sender, "❌ Koi store registered nahi hai.",
                [{"id":"REG_START","title":"🏪 Register Karen"}])

    # ── UNKNOWN ───────────────────────────────────────
    else:
        async with AsyncSessionLocal() as db:
            r = await db.execute(select(Store).where(
                Store.whatsapp_number==sender, Store.is_verified==True, Store.is_active==True))
            store = r.scalar_one_or_none()
        if store:
            await send_store_menu(sender, store.name)
        else:
            await send_welcome(sender)
from fastapi import APIRouter, Request, Response
from app.services.whatsapp_service import handle_message
import os

router = APIRouter()

@router.get("/whatsapp")
async def verify_webhook(request: Request):
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == os.getenv("WHATSAPP_VERIFY_TOKEN"):
        print("Webhook verified successfully!")
        return Response(content=challenge, media_type="text/plain")
    return Response(status_code=403)

@router.post("/whatsapp")
async def receive_message(request: Request):
    body = await request.json()
    print(f"Incoming webhook: {body}")
    try:
        entry = body.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})

        if "messages" not in value:
            return {"status": "ok"}

        message = value["messages"][0]
        sender = message["from"]
        msg_type = message.get("type")

        text = ""
        media_id = None

        if msg_type == "text":
            text = message.get("text", {}).get("body", "").strip().lower()
        elif msg_type == "image":
            media_id = message.get("image", {}).get("id")

        await handle_message(sender, text, media_id)

    except Exception as e:
        print(f"Webhook error: {e}")

    return {"status": "ok"}
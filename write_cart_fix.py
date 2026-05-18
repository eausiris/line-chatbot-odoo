import os

# Fix claude_service.py - add set_quantity intent
claude_service = '''import json
import logging
from anthropic import Anthropic
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
client = Anthropic(api_key=settings.anthropic_api_key)

SYSTEM_PROMPT = (
    "You are an AI sales assistant. Analyze customer messages and return JSON only. "
    "No other text outside JSON. "
    "Supported intents: search_product, add_to_cart, set_quantity, view_cart, create_quotation, greeting, other. "
    "IMPORTANT: Distinguish between add_to_cart (add more items) and set_quantity (set exact amount). "
    "Examples: "
    "'add 2 more' -> add_to_cart, quantity: 2. "
    "'set to 2' / 'change to 2' / 'I want only 2' / 'make it 2' -> set_quantity, quantity: 2. "
    "Return format: "
    "{\"intent\": \"search_product\", \"confidence\": 0.95, "
    "\"entities\": {\"product_name\": \"\", \"color\": \"\", \"quantity\": 1}, "
    "\"reply_if_clarify\": \"\"}"
)


async def parse_intent(user_message: str, conversation_history: list) -> dict:
    try:
        messages = list(conversation_history[-10:])
        messages.append({"role": "user", "content": user_message})

        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=messages,
        )

        raw = response.content[0].text.strip()

        if "```" in raw:
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:]

        return json.loads(raw.strip())

    except Exception as e:
        logger.error(f"Claude error: {e}")
        return {
            "intent": "other",
            "confidence": 0.0,
            "entities": {},
            "reply_if_clarify": "Please try again"
        }
'''

# Fix session_service.py - add set_cart_qty method
session_service = '''import json
import redis.asyncio as redis
from app.config import get_settings

settings = get_settings()


class SessionService:
    def __init__(self):
        self.redis = redis.from_url(settings.redis_url, decode_responses=True)
        self.ttl = settings.session_ttl_seconds

    def _key(self, user_id: str) -> str:
        return f"line_session:{user_id}"

    async def get_session(self, user_id: str) -> dict:
        try:
            data = await self.redis.get(self._key(user_id))
            if data:
                return json.loads(data)
        except Exception:
            pass
        return {"cart": [], "history": [], "last_viewed_product": None}

    async def save_session(self, user_id: str, session: dict) -> None:
        await self.redis.setex(
            self._key(user_id),
            self.ttl,
            json.dumps(session, ensure_ascii=False)
        )

    async def add_to_cart(self, user_id: str, product: dict, qty: int = 1) -> None:
        """เพิ่มจำนวนสินค้าในตะกร้า (บวกเพิ่ม)"""
        session = await self.get_session(user_id)
        for item in session["cart"]:
            if item["product_id"] == product["id"]:
                item["qty"] += qty
                await self.save_session(user_id, session)
                return
        session["cart"].append({
            "product_id": product["id"],
            "name": product["name"],
            "price_unit": product["price"],
            "qty": qty,
        })
        await self.save_session(user_id, session)

    async def set_cart_qty(self, user_id: str, product: dict, qty: int) -> None:
        """ตั้งจำนวนสินค้าในตะกร้า (set ตรงๆ)"""
        session = await self.get_session(user_id)
        for item in session["cart"]:
            if item["product_id"] == product["id"]:
                if qty <= 0:
                    session["cart"].remove(item)
                else:
                    item["qty"] = qty
                await self.save_session(user_id, session)
                return
        # ถ้ายังไม่มีในตะกร้า ให้เพิ่มใหม่
        if qty > 0:
            session["cart"].append({
                "product_id": product["id"],
                "name": product["name"],
                "price_unit": product["price"],
                "qty": qty,
            })
        await self.save_session(user_id, session)

    async def clear_cart(self, user_id: str) -> None:
        session = await self.get_session(user_id)
        session["cart"] = []
        await self.save_session(user_id, session)

    async def append_history(self, user_id: str, role: str, content: str) -> None:
        session = await self.get_session(user_id)
        session["history"].append({"role": role, "content": content})
        session["history"] = session["history"][-20:]
        await self.save_session(user_id, session)


session_service = SessionService()
'''

# Fix main.py - add set_quantity handler
main_py = '''import logging
import hashlib
import hmac
import base64
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from linebot.v3 import WebhookParser
from linebot.v3.messaging import (
    AsyncApiClient, AsyncMessagingApi, Configuration,
    ReplyMessageRequest, FlexMessage, FlexContainer, TextMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from app.config import get_settings
from app.services.claude_service import parse_intent
from app.services.odoo_service import odoo
from app.services.session_service import session_service
from app.templates.flex_messages import product_carousel, order_summary_bubble

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()

line_config = Configuration(access_token=settings.line_channel_access_token)
line_parser = WebhookParser(settings.line_channel_secret)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Bakesome Bot started")
    yield


app = FastAPI(title="LINE Odoo Bot", lifespan=lifespan)


@app.post("/webhook")
async def webhook(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()

    expected = base64.b64encode(
        hmac.new(settings.line_channel_secret.encode(), body, hashlib.sha256).digest()
    ).decode()

    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=403, detail="Invalid Signature")

    events = line_parser.parse(body.decode(), signature)

    async with AsyncApiClient(line_config) as api_client:
        line_api = AsyncMessagingApi(api_client)
        for event in events:
            if isinstance(event, MessageEvent) and isinstance(event.message, TextMessageContent):
                await handle_text_message(line_api, event)

    return {"status": "ok"}


async def handle_text_message(line_api: AsyncMessagingApi, event: MessageEvent):
    user_id = event.source.user_id
    user_text = event.message.text
    reply_token = event.reply_token

    logger.info(f"User [{user_id}]: {user_text}")

    session = await session_service.get_session(user_id)
    intent_data = await parse_intent(user_text, session["history"])
    intent = intent_data.get("intent", "other")
    entities = intent_data.get("entities", {})

    await session_service.append_history(user_id, "user", user_text)

    reply_messages = []

    if intent == "greeting":
        reply_messages = [
            TextMessage(text=f"สวัสดีครับ! ยินดีต้อนรับสู่ {settings.business_name}\\nถามถึงสินค้า ราคา หรือสั่งซื้อได้เลยครับ")
        ]

    elif intent == "search_product":
        products = odoo.search_products(
            keyword=entities.get("product_name", ""),
            category=entities.get("category", ""),
        )
        if not products:
            reply_messages = [
                TextMessage(text=f"ขออภัยครับ ไม่พบสินค้า \'{entities.get('product_name', '')}\' ลองค้นหาคำอื่นได้เลยครับ")
            ]
        else:
            session["last_viewed_product"] = products[0]
            await session_service.save_session(user_id, session)

            keyword = entities.get("product_name", "")
            domain = [["sale_ok", "=", True], ["active", "=", True]]
            if keyword:
                domain.append(["name", "ilike", keyword])
            if entities.get("category"):
                domain.append(["categ_id.name", "ilike", entities.get("category", "")])
            total_count = odoo._execute("product.template", "search_count", domain)

            reply_text = f"พบสินค้า {total_count} รายการครับ 👇"

            flex_content = product_carousel(
                products,
                total_count=total_count,
                odoo_url=settings.odoo_url,
                keyword=keyword
            )
            reply_messages = [
                TextMessage(text=reply_text),
                FlexMessage(
                    alt_text="รายการสินค้า",
                    contents=FlexContainer.from_dict(flex_content)
                )
            ]

    elif intent == "add_to_cart":
        product = session.get("last_viewed_product")
        if not product:
            reply_messages = [TextMessage(text="กรุณาเลือกสินค้าก่อนครับ 🙏")]
        else:
            qty = int(entities.get("quantity") or 1)
            await session_service.add_to_cart(user_id, product, qty=qty)
            session = await session_service.get_session(user_id)
            summary = order_summary_bubble(session["cart"])
            reply_messages = [
                TextMessage(text=f"เพิ่ม {product[\'name\']} x{qty} ลงตะกร้าแล้วครับ! 🛒"),
                FlexMessage(alt_text="ตะกร้าสินค้า",
                            contents=FlexContainer.from_dict(summary))
            ]

    elif intent == "set_quantity":
        product = session.get("last_viewed_product")
        if not product:
            reply_messages = [TextMessage(text="กรุณาเลือกสินค้าก่อนครับ 🙏")]
        else:
            qty = int(entities.get("quantity") or 1)
            await session_service.set_cart_qty(user_id, product, qty=qty)
            session = await session_service.get_session(user_id)
            summary = order_summary_bubble(session["cart"])
            reply_messages = [
                TextMessage(text=f"ปรับจำนวน {product[\'name\']} เป็น {qty} ชิ้นแล้วครับ ✅"),
                FlexMessage(alt_text="ตะกร้าสินค้า",
                            contents=FlexContainer.from_dict(summary))
            ]

    elif intent == "view_cart":
        session = await session_service.get_session(user_id)
        if not session["cart"]:
            reply_messages = [TextMessage(text="ตะกร้าของคุณยังว่างอยู่ครับ 😊")]
        else:
            summary = order_summary_bubble(session["cart"])
            reply_messages = [
                FlexMessage(alt_text="ตะกร้าสินค้า",
                            contents=FlexContainer.from_dict(summary))
            ]

    elif intent == "create_quotation":
        session = await session_service.get_session(user_id)
        if not session["cart"]:
            reply_messages = [TextMessage(text="ยังไม่มีสินค้าในตะกร้าครับ 🙏")]
        else:
            try:
                profile = await line_api.get_profile(user_id)
                display_name = profile.display_name
            except Exception:
                display_name = "LINE User"

            partner_id = odoo.get_or_create_partner(user_id, display_name)
            quotation = odoo.create_quotation(partner_id, session["cart"])
            summary = order_summary_bubble(session["cart"], quotation=quotation)
            reply_messages = [
                FlexMessage(alt_text=f"ใบเสนอราคา {quotation[\'order_name\']}",
                            contents=FlexContainer.from_dict(summary))
            ]
            await session_service.clear_cart(user_id)

    else:
        reply_messages = [
            TextMessage(text="ขออภัยครับ ลองพิมพ์ชื่อสินค้าที่ต้องการได้เลยครับ 😊")
        ]

    if reply_messages:
        await line_api.reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=reply_messages[:5])
        )

    await session_service.append_history(user_id, "assistant", f"[intent={intent}]")


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.business_name}
'''

os.makedirs("app/services", exist_ok=True)

with open("app/services/claude_service.py", "w", encoding="utf-8") as f:
    f.write(claude_service)
print("claude_service.py written")

with open("app/services/session_service.py", "w", encoding="utf-8") as f:
    f.write(session_service)
print("session_service.py written")

with open("app/main.py", "w", encoding="utf-8") as f:
    f.write(main_py)
print("main.py written")
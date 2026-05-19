import os

claude = """import json
import logging
from anthropic import Anthropic
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
client = Anthropic(api_key=settings.anthropic_api_key)

SYSTEM_PROMPT = \"\"\"You are a JSON-only intent classifier for a Thai bakery supply store chatbot.

RULES:
- Always respond with ONLY a valid JSON object
- Never use markdown code blocks
- Never add explanation or text outside the JSON
- Always include all fields

INTENTS:
- search_product: customer asks about products
- add_to_cart: customer wants to add more items to cart
- set_quantity: customer wants to change quantity to exact number
- view_cart: customer wants to see cart
- clear_cart: customer wants to clear/empty cart
- create_quotation: customer wants to confirm/order
- greeting: hello/hi
- other: anything else

EXAMPLES:
Input: "มีแป้งเค้กมั้ย"
Output: {"intent":"search_product","confidence":0.95,"entities":{"product_name":"แป้งเค้ก","category":"","quantity":1},"reply_if_clarify":""}

Input: "เพิ่มลงตะกร้า"
Output: {"intent":"add_to_cart","confidence":0.95,"entities":{"product_name":"","category":"","quantity":1},"reply_if_clarify":""}

Input: "เปลี่ยนเป็น 3 ชิ้น"
Output: {"intent":"set_quantity","confidence":0.95,"entities":{"product_name":"","category":"","quantity":3},"reply_if_clarify":""}

Input: "ล้างตะกร้า"
Output: {"intent":"clear_cart","confidence":0.99,"entities":{"product_name":"","category":"","quantity":1},"reply_if_clarify":""}

Input: "ยืนยันสั่งซื้อ"
Output: {"intent":"create_quotation","confidence":0.99,"entities":{"product_name":"","category":"","quantity":1},"reply_if_clarify":""}

Always output ONLY the JSON object, nothing else.\"\"\"


async def parse_intent(user_message: str, conversation_history: list) -> dict:
    raw = ""
    try:
        # กรอง history เฉพาะ user messages จริงๆ ไม่เอา assistant intent logs
        clean_history = [
            m for m in conversation_history[-6:]
            if m.get("role") == "user"
        ]
        clean_history.append({"role": "user", "content": user_message})

        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=256,
            system=SYSTEM_PROMPT,
            messages=clean_history,
        )

        raw = response.content[0].text.strip()
        logger.info(f"Claude raw: {raw[:200]}")

        if "```" in raw:
            raw = raw.replace("```json", "").replace("```", "").strip()

        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            raw = raw[start:end]

        result = json.loads(raw)
        logger.info(f"Claude intent: {result.get('intent')} entities: {result.get('entities')}")
        return result

    except Exception as e:
        logger.error(f"Claude error: {e}, raw: {raw[:100] if raw else 'empty'}")
        return {
            "intent": "other",
            "confidence": 0.0,
            "entities": {},
            "reply_if_clarify": ""
        }
"""

main = '''import logging
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

CLEAR_CART_KEYWORDS = ["ล้างตะกร้า", "เคลียร์ตะกร้า", "clear cart", "ลบทั้งหมด"]
VIEW_CART_KEYWORDS = ["ดูตะกร้า", "ตะกร้าของฉัน", "รายการสั่งซื้อ"]
CONFIRM_KEYWORDS = ["ยืนยันสั่งซื้อ", "ยืนยันการสั่งซื้อ"]


def detect_keyword_intent(text: str) -> str:
    t = text.lower().strip()
    for kw in CLEAR_CART_KEYWORDS:
        if kw in t:
            return "clear_cart"
    for kw in CONFIRM_KEYWORDS:
        if kw in t:
            return "create_quotation"
    for kw in VIEW_CART_KEYWORDS:
        if kw in t:
            return "view_cart"
    return ""


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Bakesome Bot started")
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

    keyword_intent = detect_keyword_intent(user_text)
    if keyword_intent:
        intent = keyword_intent
        entities = {}
    else:
        intent_data = await parse_intent(user_text, session["history"])
        intent = intent_data.get("intent", "other")
        entities = intent_data.get("entities", {})

    # บันทึก history เฉพาะ user message (ไม่บันทึก assistant intent)
    await session_service.append_history(user_id, "user", user_text)

    reply_messages = []

    if intent == "greeting":
        reply_messages = [
            TextMessage(text=f"สวัสดีครับ! ยินดีต้อนรับสู่ {settings.business_name}\\nถามถึงสินค้า ราคา หรือสั่งซื้อได้เลยครับ")
        ]

    elif intent == "search_product":
        keyword = entities.get("product_name", "")
        products = odoo.search_products(
            keyword=keyword,
            category=entities.get("category", ""),
        )
        if not products:
            reply_messages = [
                TextMessage(text=f"ขออภัยครับ ไม่พบ \'{keyword}\' ลองค้นหาคำอื่นได้เลยครับ")
            ]
        else:
            session["last_viewed_product"] = products[0]
            await session_service.save_session(user_id, session)

            domain = [["sale_ok", "=", True], ["active", "=", True]]
            if keyword:
                domain.append(["name", "ilike", keyword])
            if entities.get("category"):
                domain.append(["categ_id.name", "ilike", entities.get("category", "")])
            total_count = odoo._execute("product.template", "search_count", domain)

            reply_text = f"มี{keyword} {total_count} รายการครับ 👇" if keyword else f"พบสินค้า {total_count} รายการครับ 👇"

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

    elif intent == "clear_cart":
        await session_service.clear_cart(user_id)
        reply_messages = [TextMessage(text="ล้างตะกร้าแล้วครับ 🗑️")]

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


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.business_name}
'''

os.makedirs("app/services", exist_ok=True)

with open("app/services/claude_service.py", "w", encoding="utf-8") as f:
    f.write(claude)
print("claude_service.py written")

with open("app/main.py", "w", encoding="utf-8") as f:
    f.write(main)
print("app/main.py written")
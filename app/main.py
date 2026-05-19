import logging
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

CLEAR_CART_EXACT = ["ล้างตะกร้า", "เคลียร์ตะกร้า", "clear cart"]
CONFIRM_EXACT = ["ยืนยันสั่งซื้อ", "ยืนยันการสั่งซื้อ"]


def detect_keyword_intent(text: str) -> str:
    t = text.strip()
    if t in CLEAR_CART_EXACT:
        return "clear_cart"
    if t in CONFIRM_EXACT:
        return "create_quotation"
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
    expected = base64.b64encode(hmac.new(settings.line_channel_secret.encode(), body, hashlib.sha256).digest()).decode()
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

    await session_service.append_history(user_id, "user", user_text)

    reply_messages = []

    if intent == "greeting":
        reply_messages = [TextMessage(text=f"สวัสดีครับ! ยินดีต้อนรับสู่ {settings.business_name}\nถามถึงสินค้า ราคา หรือสั่งซื้อได้เลยครับ")]

    elif intent == "search_product":
        keyword = entities.get("product_name", "")
        products = odoo.search_products(keyword=keyword, category=entities.get("category", ""))
        if not products:
            reply_messages = [TextMessage(text=f"ขออภัยครับ ไม่พบ '{keyword}' ลองค้นหาคำอื่นได้เลยครับ")]
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
            flex_content = product_carousel(products, total_count=total_count, odoo_url=settings.odoo_url, keyword=keyword)
            reply_messages = [
                TextMessage(text=reply_text),
                FlexMessage(alt_text="รายการสินค้า", contents=FlexContainer.from_dict(flex_content))
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
                TextMessage(text=f"เพิ่ม {product['name']} x{qty} ลงตะกร้าแล้วครับ! 🛒"),
                FlexMessage(alt_text="ตะกร้าสินค้า", contents=FlexContainer.from_dict(summary))
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
                TextMessage(text=f"ปรับจำนวน {product['name']} เป็น {qty} ชิ้นแล้วครับ ✅"),
                FlexMessage(alt_text="ตะกร้าสินค้า", contents=FlexContainer.from_dict(summary))
            ]

    elif intent == "view_cart":
        session = await session_service.get_session(user_id)
        if not session["cart"]:
            reply_messages = [TextMessage(text="ตะกร้าของคุณยังว่างอยู่ครับ 😊")]
        else:
            summary = order_summary_bubble(session["cart"])
            reply_messages = [FlexMessage(alt_text="ตะกร้าสินค้า", contents=FlexContainer.from_dict(summary))]

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
            reply_messages = [FlexMessage(alt_text=f"ใบเสนอราคา {quotation['order_name']}", contents=FlexContainer.from_dict(summary))]
            await session_service.clear_cart(user_id)

    else:
        reply_messages = [TextMessage(text="ขออภัยครับ ลองพิมพ์ชื่อสินค้าที่ต้องการได้เลยครับ 😊")]

    if reply_messages:
        await line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=reply_messages[:5]))


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.business_name}

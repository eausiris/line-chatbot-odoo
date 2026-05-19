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
- clear_cart: customer wants to clear/empty cart (ล้างตะกร้า/เคลียร์ตะกร้า)
- create_quotation: customer wants to confirm/order (ยืนยัน/สั่งซื้อ)
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
    try:
        messages = list(conversation_history[-6:])
        messages.append({"role": "user", "content": user_message})

        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=256,
            system=SYSTEM_PROMPT,
            messages=messages,
        )

        raw = response.content[0].text.strip()
        logger.info(f"Claude raw: {raw[:300]}")

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
        logger.error(f"Claude error: {e}")
        return {
            "intent": "other",
            "confidence": 0.0,
            "entities": {},
            "reply_if_clarify": ""
        }
"""

flex = '''NO_IMAGE_URL = "https://placehold.co/400x300/f0f0f0/999999?text=No+Image"


def product_card(product: dict, odoo_url: str = "") -> dict:
    uom = product.get("uom", "ชิ้น")
    image_url = product.get("image_url") or NO_IMAGE_URL
    product_url = f"{odoo_url}/shop/product/{product[\'template_id\']}" if odoo_url else ""

    variant_rows = []
    for v in product.get("variants", [])[:5]:
        color = "#27AE60" if v["stock"] > 0 else "#E74C3C"
        variant_rows.append({
            "type": "box", "layout": "horizontal",
            "contents": [
                {"type": "text", "text": v["uom"], "size": "xs", "color": "#34495E", "flex": 2},
                {"type": "text", "text": f"\\u0e3f{v[\'price\']:,.0f}", "size": "xs",
                 "color": "#E74C3C", "align": "center", "flex": 2},
                {"type": "text", "text": f"{v[\'stock\']} {v[\'uom\']}", "size": "xs",
                 "color": color, "align": "end", "flex": 2},
            ],
        })

    stock_rows = []
    for wh in product.get("stock_by_warehouse", []):
        color = "#27AE60" if wh["qty"] > 0 else "#E74C3C"
        stock_rows.append({
            "type": "box", "layout": "horizontal",
            "contents": [
                {"type": "text", "text": f"\\u2022 {wh[\'warehouse\']}", "size": "xs",
                 "color": "#7F8C8D", "flex": 3},
                {"type": "text", "text": f"{wh[\'qty\']} {uom}", "size": "xs",
                 "color": color, "align": "end", "flex": 1},
            ],
        })

    body_contents = [
        {"type": "text", "text": product["name"],
         "weight": "bold", "size": "lg", "wrap": True, "color": "#1A1A2E"},
        {"type": "box", "layout": "baseline", "contents": [
            {"type": "text", "text": "ราคา", "color": "#95A5A6", "size": "sm", "flex": 0},
            {"type": "text", "text": f"\\u0e3f{product[\'price\']:,.0f}/{uom} (VAT)",
             "weight": "bold", "size": "md", "color": "#E74C3C", "flex": 1, "align": "end"},
        ]},
        {"type": "separator"},
    ]

    if variant_rows:
        body_contents.append({
            "type": "text", "text": "\\U0001f4e6 Package / หน่วย",
            "size": "xs", "color": "#2C3E50", "weight": "bold"
        })
        body_contents.append({
            "type": "box", "layout": "horizontal",
            "contents": [
                {"type": "text", "text": "หน่วย", "size": "xs", "color": "#BDC3C7", "flex": 2},
                {"type": "text", "text": "ราคา", "size": "xs", "color": "#BDC3C7", "align": "center", "flex": 2},
                {"type": "text", "text": "คงเหลือ", "size": "xs", "color": "#BDC3C7", "align": "end", "flex": 2},
            ],
        })
        body_contents.extend(variant_rows)
        body_contents.append({"type": "separator"})

    if stock_rows:
        body_contents.append({
            "type": "text", "text": "\\U0001f3ea สต็อกแยกสาขา",
            "size": "xs", "color": "#2C3E50", "weight": "bold"
        })
        body_contents.extend(stock_rows)

    footer_buttons = [
        {
            "type": "button", "style": "primary", "color": "#1A1A2E", "height": "sm",
            "action": {
                "type": "message", "label": "\\U0001f6d2 เพิ่มลงตะกร้า",
                "text": f"เพิ่มสินค้า {product[\'name\']} ลงตะกร้า",
            },
        },
    ]

    if product_url:
        footer_buttons.append({
            "type": "button", "style": "secondary", "height": "sm",
            "action": {
                "type": "uri", "label": "\\U0001f4cb รายละเอียด",
                "uri": product_url,
            },
        })

    return {
        "type": "bubble", "size": "mega",
        "hero": {
            "type": "image",
            "url": image_url,
            "size": "full",
            "aspectRatio": "4:3",
            "aspectMode": "cover",
            "action": {"type": "uri", "label": "view", "uri": image_url},
        },
        "body": {
            "type": "box", "layout": "vertical",
            "spacing": "sm", "paddingAll": "16px",
            "contents": body_contents,
        },
        "footer": {
            "type": "box", "layout": "vertical",
            "spacing": "sm", "paddingAll": "12px",
            "contents": footer_buttons,
        },
    }


def view_all_card(total_count: int, odoo_url: str = "", keyword: str = "") -> dict:
    import urllib.parse
    search_url = f"{odoo_url}/shop?search={urllib.parse.quote(keyword)}" if odoo_url and keyword else f"{odoo_url}/shop" if odoo_url else "https://odoo.com"
    return {
        "type": "bubble", "size": "mega",
        "body": {
            "type": "box", "layout": "vertical",
            "justifyContent": "center",
            "contents": [
                {"type": "text", "text": "\\U0001f6d2", "size": "5xl", "align": "center"},
                {"type": "text", "text": f"มีสินค้าทั้งหมด\\n{total_count} รายการ",
                 "weight": "bold", "size": "xl", "align": "center", "wrap": True, "color": "#1A1A2E"},
                {"type": "text", "text": "กดเพื่อดูสินค้าทั้งหมด",
                 "size": "sm", "color": "#7F8C8D", "align": "center"},
            ],
        },
        "footer": {
            "type": "box", "layout": "vertical",
            "contents": [{
                "type": "button", "style": "primary", "color": "#E74C3C",
                "action": {"type": "uri", "label": "\\U0001f4e6 ดูสินค้าทั้งหมด", "uri": search_url},
            }],
        },
    }


def product_carousel(products: list, total_count: int = 0, odoo_url: str = "", keyword: str = "") -> dict:
    MAX_SHOW = 9
    bubbles = [product_card(p, odoo_url) for p in products[:MAX_SHOW]]
    if total_count > len(products) or len(products) > MAX_SHOW:
        bubbles.append(view_all_card(total_count or len(products), odoo_url, keyword))
    return {"type": "carousel", "contents": bubbles}


def order_summary_bubble(cart_items: list, quotation: dict = None) -> dict:
    line_contents = []
    total = 0
    for item in cart_items:
        item_total = item["price_unit"] * item["qty"]
        total += item_total
        line_contents.append({
            "type": "box", "layout": "horizontal",
            "contents": [
                {"type": "text",
                 "text": f"{item[\'name\']} x{item[\'qty\']}",
                 "size": "sm", "color": "#2C3E50", "flex": 3, "wrap": True},
                {"type": "text", "text": f"\\u0e3f{item_total:,.0f}",
                 "size": "sm", "align": "end", "flex": 1},
            ],
        })

    if quotation:
        warn_rows = [
            {"type": "text", "text": f"\\u26a0\\ufe0f {w}",
             "size": "xs", "color": "#E67E22", "wrap": True}
            for w in quotation.get("warnings", [])
        ]
        footer_contents = [
            {"type": "text", "text": f"\\u2705 เลขที่: {quotation[\'order_name\']}",
             "weight": "bold", "color": "#27AE60", "align": "center"},
            *warn_rows,
            {"type": "button", "style": "primary", "color": "#27AE60",
             "action": {"type": "uri", "label": "\\U0001f4c4 ดูใบเสนอราคา",
                        "uri": quotation["portal_url"]}},
        ]
    else:
        footer_contents = [
            {"type": "button", "style": "primary", "color": "#E74C3C",
             "action": {"type": "message", "label": "\\u2705 ยืนยันสั่งซื้อ", "text": "ยืนยันสั่งซื้อ"}},
            {"type": "button", "style": "secondary",
             "action": {"type": "message", "label": "\\U0001f5d1 ล้างตะกร้า", "text": "ล้างตะกร้า"}},
        ]

    return {
        "type": "bubble",
        "header": {
            "type": "box", "layout": "vertical", "backgroundColor": "#1A1A2E",
            "contents": [{"type": "text", "text": "\\U0001f6d2 รายการสินค้า",
                          "color": "#FFFFFF", "weight": "bold", "size": "md"}],
        },
        "body": {
            "type": "box", "layout": "vertical", "spacing": "md",
            "contents": [
                *line_contents,
                {"type": "separator"},
                {"type": "box", "layout": "horizontal", "contents": [
                    {"type": "text", "text": "ยอดรวม (VAT)",
                     "weight": "bold", "size": "md", "color": "#2C3E50"},
                    {"type": "text", "text": f"\\u0e3f{total:,.2f}",
                     "weight": "bold", "size": "md", "color": "#E74C3C", "align": "end"},
                ]},
            ],
        },
        "footer": {
            "type": "box", "layout": "vertical", "spacing": "sm",
            "contents": footer_contents,
        },
    }
'''

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

    await session_service.append_history(user_id, "assistant", f"[intent={intent}]")


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.business_name}
'''

os.makedirs("app/services", exist_ok=True)
os.makedirs("app/templates", exist_ok=True)

with open("app/services/claude_service.py", "w", encoding="utf-8") as f:
    f.write(claude)
print("claude_service.py written")

with open("app/templates/flex_messages.py", "w", encoding="utf-8") as f:
    f.write(flex)
print("flex_messages.py written")

with open("app/main.py", "w", encoding="utf-8") as f:
    f.write(main)
print("main.py written")
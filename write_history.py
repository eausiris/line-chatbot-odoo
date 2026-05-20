import os

odoo_service = '''import xmlrpc.client
import logging
import urllib.request
import urllib.parse
import json
from typing import Optional
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

IMAGE_CACHE = {}


def upload_image_to_host(img_b64: str, product_id: int) -> Optional[str]:
    if product_id in IMAGE_CACHE:
        return IMAGE_CACHE[product_id]
    try:
        post_data = urllib.parse.urlencode({
            'key': '6d207e02198a847aa98d0a2a901485a5',
            'action': 'upload',
            'source': img_b64,
            'format': 'json'
        }).encode('utf-8')
        req = urllib.request.Request(
            'https://freeimage.host/api/1/upload',
            data=post_data, method='POST'
        )
        req.add_header('Content-Type', 'application/x-www-form-urlencoded')
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
        url = result['image']['url']
        IMAGE_CACHE[product_id] = url
        logger.info(f"Image uploaded: {url}")
        return url
    except Exception as e:
        logger.error(f"Image upload error: {e}")
        return None


class OdooService:
    def __init__(self):
        self.url = settings.odoo_url
        self.db = settings.odoo_db
        self.username = settings.odoo_username
        self.password = settings.odoo_password
        self._uid: Optional[int] = None
        self._common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self._models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")

    @property
    def uid(self) -> int:
        if not self._uid:
            self._uid = self._common.authenticate(
                self.db, self.username, self.password, {}
            )
            if not self._uid:
                raise ConnectionError("Odoo login failed!")
            logger.info(f"Odoo login OK uid={self._uid}")
        return self._uid

    def _execute(self, model, method, *args, **kwargs):
        try:
            return self._models.execute_kw(
                self.db, self.uid, self.password,
                model, method, list(args), kwargs
            )
        except Exception as e:
            logger.error(f"Odoo error [{model}.{method}]: {e}")
            raise

    def get_customer_history(self, line_user_id: str) -> dict:
        """ดึงประวัติการซื้อของลูกค้าจาก LINE user ID"""
        try:
            # หา partner
            partner_ids = self._execute(
                "res.partner", "search",
                [["ref", "=", f"LINE:{line_user_id}"]]
            )
            if not partner_ids:
                return {"is_returning": False, "name": "", "last_products": [], "order_count": 0}

            partner = self._execute(
                "res.partner", "read", partner_ids,
                fields=["id", "name"]
            )[0]

            # หา orders ของลูกค้าคนนี้
            order_ids = self._execute(
                "sale.order", "search",
                [["partner_id", "=", partner["id"]], ["state", "in", ["sale", "done"]]],
                limit=5,
                order="date_order desc"
            )

            if not order_ids:
                return {"is_returning": True, "name": partner["name"], "last_products": [], "order_count": 0}

            # ดึงสินค้าจาก order ล่าสุด
            last_order = self._execute(
                "sale.order", "read", [order_ids[0]],
                fields=["name", "order_line", "date_order"]
            )[0]

            last_products = []
            if last_order.get("order_line"):
                lines = self._execute(
                    "sale.order.line", "read", last_order["order_line"][:5],
                    fields=["product_id", "product_uom_qty"]
                )
                for l in lines:
                    last_products.append({
                        "name": l["product_id"][1] if l.get("product_id") else "",
                        "qty": int(l.get("product_uom_qty", 1))
                    })

            return {
                "is_returning": True,
                "name": partner["name"],
                "last_products": last_products,
                "order_count": len(order_ids),
                "last_order_name": last_order["name"]
            }

        except Exception as e:
            logger.error(f"Customer history error: {e}")
            return {"is_returning": False, "name": "", "last_products": [], "order_count": 0}

    def get_stock_by_warehouse(self, product_id: int) -> list:
        try:
            warehouse_ids = self._execute(
                "stock.warehouse", "search", [["active", "=", True]]
            )
            warehouses = self._execute(
                "stock.warehouse", "read", warehouse_ids,
                fields=["id", "name", "lot_stock_id"]
            )
            result = []
            for wh in warehouses:
                location_id = wh["lot_stock_id"][0] if wh.get("lot_stock_id") else False
                if not location_id:
                    continue
                quant_ids = self._execute(
                    "stock.quant", "search",
                    [["product_id", "=", product_id], ["location_id", "=", location_id]]
                )
                qty = 0
                if quant_ids:
                    quants = self._execute(
                        "stock.quant", "read", quant_ids,
                        fields=["quantity", "reserved_quantity"]
                    )
                    qty = sum(q["quantity"] - q.get("reserved_quantity", 0) for q in quants)
                result.append({"warehouse": wh["name"], "qty": int(max(qty, 0))})
            return result
        except Exception as e:
            logger.error(f"Stock by warehouse error: {e}")
            return []

    def get_product_variants(self, template_id: int) -> list:
        try:
            variant_ids = self._execute(
                "product.product", "search",
                [["product_tmpl_id", "=", template_id], ["active", "=", True]]
            )
            if not variant_ids:
                return []
            variants = self._execute(
                "product.product", "read", variant_ids,
                fields=["id", "display_name", "lst_price", "uom_id", "qty_available"]
            )
            return [{
                "id": v["id"],
                "name": v["display_name"],
                "price": v["lst_price"],
                "uom": v["uom_id"][1] if v.get("uom_id") else "ชิ้น",
                "stock": int(v.get("qty_available", 0)),
            } for v in variants]
        except Exception as e:
            logger.error(f"Variants error: {e}")
            return []

    def search_products(self, keyword="", category="", limit=5):
        domain = [["sale_ok", "=", True], ["active", "=", True]]
        if keyword:
            domain.append(["name", "ilike", keyword])
        if category:
            domain.append(["categ_id.name", "ilike", category])

        ids = self._execute("product.template", "search", domain, limit=limit)
        if not ids:
            return []

        products = self._execute(
            "product.template", "read", ids,
            fields=["id", "name", "description_sale", "list_price",
                    "qty_available", "categ_id", "product_variant_ids",
                    "uom_id", "image_512"]
        )

        result = []
        for p in products:
            variant_id = p["product_variant_ids"][0] if p.get("product_variant_ids") else p["id"]
            variants = self.get_product_variants(p["id"])
            stock_by_warehouse = self.get_stock_by_warehouse(variant_id)
            image_url = None
            if p.get("image_512"):
                image_url = upload_image_to_host(p["image_512"], p["id"])

            result.append({
                "id": variant_id,
                "template_id": p["id"],
                "name": p["name"],
                "description": p.get("description_sale") or "",
                "price": p["list_price"],
                "stock": int(p.get("qty_available", 0)),
                "stock_by_warehouse": stock_by_warehouse,
                "category": p["categ_id"][1] if p.get("categ_id") else "-",
                "uom": p["uom_id"][1] if p.get("uom_id") else "ชิ้น",
                "variants": variants,
                "image_url": image_url,
            })
        return result

    def get_or_create_partner(self, line_user_id, display_name):
        ids = self._execute(
            "res.partner", "search",
            [["ref", "=", f"LINE:{line_user_id}"]]
        )
        if ids:
            return ids[0]
        return self._execute("res.partner", "create", {
            "name": display_name,
            "ref": f"LINE:{line_user_id}",
            "customer_rank": 1,
        })

    def check_stock_sufficient(self, product_id: int, qty_needed: int) -> dict:
        stock_list = self.get_stock_by_warehouse(product_id)
        total = sum(w["qty"] for w in stock_list)
        sufficient = [w for w in stock_list if w["qty"] >= qty_needed]
        return {
            "total_stock": total,
            "is_sufficient": total >= qty_needed,
            "sufficient_warehouses": sufficient,
            "stock_by_warehouse": stock_list,
        }

    def create_quotation(self, partner_id, cart_items, note=""):
        order_lines = []
        warnings = []
        for item in cart_items:
            stock_info = self.check_stock_sufficient(item["product_id"], item["qty"])
            if not stock_info["is_sufficient"]:
                warnings.append(
                    f"{item[\'name\']}: ต้องการ {item[\'qty\']} มีแค่ {stock_info[\'total_stock\']}"
                )
            order_lines.append((0, 0, {
                "product_id": item["product_id"],
                "product_uom_qty": item["qty"],
                "price_unit": item["price_unit"],
            }))
        order_id = self._execute("sale.order", "create", {
            "partner_id": partner_id,
            "order_line": order_lines,
            "note": note or "Order from LINE OA Bot",
            "origin": "LINE OA Chatbot",
        })
        data = self._execute(
            "sale.order", "read", [order_id],
            fields=["name", "amount_total"]
        )[0]
        return {
            "order_id": order_id,
            "order_name": data["name"],
            "amount_total": data["amount_total"],
            "portal_url": f"{self.url}/my/orders/{order_id}",
            "warnings": warnings,
        }


odoo = OdooService()
'''

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

CLEAR_CART_EXACT = ["ล้างตะกร้า", "เคลียร์ตะกร้า", "clear cart"]
CONFIRM_EXACT = ["ยืนยันสั่งซื้อ", "ยืนยันการสั่งซื้อ"]


def detect_keyword_intent(text: str) -> str:
    t = text.strip()
    if t in CLEAR_CART_EXACT:
        return "clear_cart"
    if t in CONFIRM_EXACT:
        return "create_quotation"
    return ""


def build_greeting(history: dict, business_name: str) -> str:
    """สร้างข้อความทักทายตามประวัติลูกค้า"""
    if not history.get("is_returning") or not history.get("last_products"):
        return f"สวัสดีครับ! ยินดีต้อนรับสู่ {business_name}\\nถามถึงสินค้า ราคา หรือสั่งซื้อได้เลยครับ"

    name = history["name"]
    products = history["last_products"]
    order_count = history.get("order_count", 0)

    # สร้างรายการสินค้าล่าสุด
    product_list = ", ".join(f"{p[\'name\']} x{p[\'qty\']}" for p in products[:3])

    greeting = f"สวัสดีคุณ{name}ครับ! ยินดีต้อนรับกลับมา 😊\\n"
    greeting += f"ครั้งที่แล้วคุณซื้อ {product_list}\\n"
    greeting += f"อยากสั่งซ้ำหรือมีอะไรให้ช่วยไหมครับ?"

    return greeting


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
        # ดึงประวัติลูกค้า
        history = odoo.get_customer_history(user_id)
        greeting_text = build_greeting(history, settings.business_name)
        reply_messages = [TextMessage(text=greeting_text)]

        # ถ้าเป็นลูกค้าเก่า ถามว่าอยากสั่งซ้ำไหม
        if history.get("is_returning") and history.get("last_products"):
            reply_messages.append(
                TextMessage(text=f"พิมพ์ชื่อสินค้าที่ต้องการ หรือพิมพ์ \'{history[\'last_products\'][0][\'name\']}\' เพื่อค้นหาสินค้าเดิมได้เลยครับ 👇")
            )

    elif intent == "search_product":
        keyword = entities.get("product_name", "")
        products = odoo.search_products(keyword=keyword, category=entities.get("category", ""))
        if not products:
            reply_messages = [TextMessage(text=f"ขออภัยครับ ไม่พบ \'{keyword}\' ลองค้นหาคำอื่นได้เลยครับ")]
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
                TextMessage(text=f"เพิ่ม {product[\'name\']} x{qty} ลงตะกร้าแล้วครับ! 🛒"),
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
                TextMessage(text=f"ปรับจำนวน {product[\'name\']} เป็น {qty} ชิ้นแล้วครับ ✅"),
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
            reply_messages = [FlexMessage(alt_text=f"ใบเสนอราคา {quotation[\'order_name\']}", contents=FlexContainer.from_dict(summary))]
            await session_service.clear_cart(user_id)

    else:
        reply_messages = [TextMessage(text="ขออภัยครับ ลองพิมพ์ชื่อสินค้าที่ต้องการได้เลยครับ 😊")]

    if reply_messages:
        await line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=reply_messages[:5]))


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.business_name}
'''

os.makedirs("app/services", exist_ok=True)

with open("app/services/odoo_service.py", "w", encoding="utf-8") as f:
    f.write(odoo_service)
print("odoo_service.py written")

with open("app/main.py", "w", encoding="utf-8") as f:
    f.write(main_py)
print("app/main.py written")
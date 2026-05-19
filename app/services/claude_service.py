import json
import logging
from anthropic import Anthropic
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
client = Anthropic(api_key=settings.anthropic_api_key)

SYSTEM_PROMPT = """You are a JSON-only intent classifier for a Thai bakery supply store.

OUTPUT: Always respond with ONLY a valid JSON object. No markdown. No explanation.

INTENTS:
- search_product: customer mentions product names to search (e.g. "บัวแดง", "แป้งเค้ก", "เนย")
- add_to_cart: customer says เพิ่มลงตะกร้า (from button click)
- set_quantity: change to exact number (เปลี่ยนเป็น/ขอแค่/เอาแค่/แก้เป็น)
- view_cart: see cart (ดูตะกร้า)
- clear_cart: ล้างตะกร้า ONLY - exact phrase
- create_quotation: ยืนยันสั่งซื้อ ONLY - exact phrase
- greeting: สวัสดี/hello
- other: everything else

CRITICAL RULE: "บัวแดง 2 พัดโบก 1" = search_product (product names with quantities = search)
CRITICAL RULE: clear_cart ONLY when message is exactly "ล้างตะกร้า" or "เคลียร์ตะกร้า"

JSON format:
{"intent":"search_product","confidence":0.95,"entities":{"product_name":"","category":"","quantity":1},"reply_if_clarify":""}

EXAMPLES:
"มีแป้งเค้กมั้ย" -> {"intent":"search_product","confidence":0.95,"entities":{"product_name":"แป้งเค้ก","category":"","quantity":1},"reply_if_clarify":""}
"บัวแดง 2 พัดโบก 1" -> {"intent":"search_product","confidence":0.90,"entities":{"product_name":"บัวแดง","category":"","quantity":2},"reply_if_clarify":""}
"เพิ่มสินค้า X ลงตะกร้า" -> {"intent":"add_to_cart","confidence":0.99,"entities":{"product_name":"X","category":"","quantity":1},"reply_if_clarify":""}
"เปลี่ยนเป็น 3 ชิ้น" -> {"intent":"set_quantity","confidence":0.95,"entities":{"product_name":"","category":"","quantity":3},"reply_if_clarify":""}
"ล้างตะกร้า" -> {"intent":"clear_cart","confidence":0.99,"entities":{"product_name":"","category":"","quantity":1},"reply_if_clarify":""}
"ยืนยันสั่งซื้อ" -> {"intent":"create_quotation","confidence":0.99,"entities":{"product_name":"","category":"","quantity":1},"reply_if_clarify":""}
"""


async def parse_intent(user_message: str, conversation_history: list) -> dict:
    raw = ""
    try:
        clean_history = [m for m in conversation_history[-4:] if m.get("role") == "user"]
        clean_history.append({"role": "user", "content": user_message})

        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=200,
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
        return {"intent": "other", "confidence": 0.0, "entities": {}, "reply_if_clarify": ""}

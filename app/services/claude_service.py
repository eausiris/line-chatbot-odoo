import json
import logging
from anthropic import Anthropic
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
client = Anthropic(api_key=settings.anthropic_api_key)

SYSTEM_PROMPT = """You are a JSON-only intent classifier for a Thai bakery supply store chatbot.

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

Always output ONLY the JSON object, nothing else."""


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

content = """import json
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

Input: "ดูตะกร้า"
Output: {"intent":"view_cart","confidence":0.95,"entities":{"product_name":"","category":"","quantity":1},"reply_if_clarify":""}

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

        # Strip markdown if present
        if "```" in raw:
            raw = raw.replace("```json", "").replace("```", "").strip()

        # Extract JSON object
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            raw = raw[start:end]

        result = json.loads(raw)
        logger.info(f"Claude intent: {result.get('intent')} entities: {result.get('entities')}")
        return result

    except Exception as e:
        logger.error(f"Claude error: {e}, raw: {raw if 'raw' in dir() else 'N/A'}")
        return {
            "intent": "other",
            "confidence": 0.0,
            "entities": {},
            "reply_if_clarify": ""
        }
"""

with open("app/services/claude_service.py", "w", encoding="utf-8") as f:
    f.write(content)
print("claude_service.py written")
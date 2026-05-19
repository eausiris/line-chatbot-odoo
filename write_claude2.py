content = """import json
import logging
from anthropic import Anthropic
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
client = Anthropic(api_key=settings.anthropic_api_key)

SYSTEM_PROMPT = (
    "You are an AI assistant for a bakery supply store in Thailand. "
    "Analyze customer messages and return ONLY a JSON object, nothing else. "
    "No markdown, no explanation, no Thai text outside JSON. "
    "JSON format: "
    '{\"intent\":\"search_product\",\"confidence\":0.95,\"entities\":{\"product_name\":\"\",\"category\":\"\",\"quantity\":1},\"reply_if_clarify\":\"\"} '
    "Intents: search_product, add_to_cart, set_quantity, view_cart, create_quotation, greeting, other. "
    "set_quantity = change to exact number. add_to_cart = add more."
)


async def parse_intent(user_message: str, conversation_history: list) -> dict:
    try:
        messages = list(conversation_history[-10:])
        messages.append({"role": "user", "content": user_message})

        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=256,
            system=SYSTEM_PROMPT,
            messages=messages,
        )

        raw = response.content[0].text.strip()
        logger.info(f"Claude raw response: {raw[:200]}")

        # Strip markdown
        if "```" in raw:
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        # Extract JSON object
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            raw = raw[start:end]

        return json.loads(raw)

    except Exception as e:
        logger.error(f"Claude error: {e}")
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